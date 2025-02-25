##############################################################################
#
#    Copyright (C) 2016 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import base64
import logging

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, api, fields

from odoo.addons.sbc_compassion.models.correspondence_page import (
    BOX_SEPARATOR,
    PAGE_SEPARATOR,
)
from functools import reduce

_logger = logging.getLogger(__name__)


class Correspondence(models.Model):
    _inherit = "correspondence"

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################
    letter_delivery_preference = fields.Selection(
        related="partner_id.letter_delivery_preference"
    )
    communication_id = fields.Many2one(
        "partner.communication.job", "Communication", readonly=False
    )
    email_id = fields.Many2one(
        "mail.mail",
        "E-mail",
        related="communication_id.email_id",
        store=True,
        index=True,
        readonly=False,
    )
    communication_state = fields.Selection(related="communication_id.state")
    sent_date = fields.Datetime(
        "Communication sent",
        related="communication_id.sent_date",
        store=True,
        track_visibility="onchange",
    )
    email_read = fields.Datetime(
        compute="_compute_email_read", inverse="_inverse_email_read", store=True)
    zip_file = fields.Binary(oldname="zip_id", attachment=True)
    has_valid_language = fields.Boolean(compute="_compute_valid_language", store=True)

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################
    def _compute_letter_format(self):
        """ Letter is zip if it contains a zip attachment"""
        for letter in self:
            if letter.zip_file:
                letter.letter_format = "zip"
            else:
                super(Correspondence, letter)._compute_letter_format()

    @api.multi
    @api.depends(
        "supporter_languages_ids",
        "page_ids",
        "page_ids.translated_text",
        "translation_language_id",
    )
    def _compute_valid_language(self):
        """ Detect if text is written in the language corresponding to the
        language_id """
        for letter in self:
            letter.has_valid_language = False
            if letter.translated_text and letter.translation_language_id:
                s = (
                    letter.translated_text.strip(" \t\n\r.")
                    .replace(BOX_SEPARATOR, "")
                    .replace(PAGE_SEPARATOR, "")
                )
                if s:
                    # find the language of text argument
                    lang = self.env["crm.claim"].detect_lang(letter.translated_text)
                    letter.has_valid_language = (
                        lang and lang in letter.supporter_languages_ids
                    )

    @api.multi
    @api.depends("communication_id.email_id.mail_tracking_ids.tracking_event_ids")
    def _compute_email_read(self):
        for mail in self:
            dates = [
                x.time
                for x in mail.communication_id.email_id.tracking_event_ids
                if x.event_type in ("open", "delivered")
            ]
            if dates:
                mail.email_read = max(dates)

    def _inverse_email_read(self):
        return True

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################

    def get_image(self):
        """ Method for retrieving the image """
        self.ensure_one()
        if self.zip_file:
            data = base64.b64decode(self.zip_file)
        else:
            data = super().get_image()
        return data

    @api.multi
    def attach_zip(self):
        """
        When a partner gets multiple letters, we make a zip and attach it
        to the first letter, so that he can only download this zip.
        :return: True
        """
        if len(self) > 5:
            _zip = (
                self.env["correspondence.download.wizard"]
                    .with_context(active_model=self._name, active_ids=self.ids)
                    .create({})
            )
            _zip.get_letters()
            self.write({"zip_file": False})
            letter_attach = self[:1]
            letter_attach.write(
                {"zip_file": _zip.download_data, "letter_format": "zip"}
            )
            base_url = self.env["ir.config_parameter"].sudo().get_param(
                "web.external.url")
            self.write({"read_url": f"{base_url}/b2s_image?id={letter_attach.uuid}"})
        return True

    @api.multi
    def compose_letter_image(self):
        """
        Regenerate communication if already existing
        """
        res = super().compose_letter_image()
        if self.communication_id:
            self.communication_id.refresh_text()
        return res

    @api.multi
    def send_communication(self):
        """
        Sends the communication to the partner. By default it won't do
        anything if a communication is already attached to the letter.
        Context can contain following settings :
            - comm_vals : dictionary for communication values
            - force_send : will send the communication regardless of the
                           settings.
            - overwrite : will force the communication creation even if one
                          already exists.
        :return: True
        """
        partners = self.mapped("partner_id")
        final_letter = self.env.ref("sbc_compassion.correspondence_type_final")
        module = "partner_communication_switzerland."
        first_letter_template = self.env.ref(module + "config_onboarding_first_letter")
        final_template = self.env.ref(module + "child_letter_final_config")
        new_template = self.env.ref(module + "child_letter_config")
        old_template = self.env.ref(
            module + "child_letter_old_config"
        )
        old_limit = datetime.today() - relativedelta(months=2)

        for partner in partners:
            letters = self.filtered(lambda l: l.partner_id == partner)
            is_first = self.filtered(
                lambda l: l.communication_type_ids == self.env.ref(
                    "sbc_compassion.correspondence_type_new_sponsor"))
            no_comm = letters.filtered(lambda l: not l.communication_id)
            to_generate = letters if self.env.context.get("overwrite") else no_comm

            final_letters = to_generate.filtered(
                lambda l: final_letter in l.communication_type_ids
            )
            new_letters = to_generate - final_letters
            old_letters = new_letters.filtered(lambda l: l.create_date < old_limit)
            new_letters -= old_letters

            final_letters._generate_communication(final_template)
            new_letters._generate_communication(
                first_letter_template if is_first else new_template)
            old_letters._generate_communication(
                first_letter_template if is_first else old_template)

        if self.env.context.get("force_send"):
            self.mapped("communication_id").filtered(lambda c: c.state != "done").send()

        return True

    @api.multi
    def send_unread_b2s(self):
        """
        IR Action Rule called 3 days after correspondence is sent
        by e-mail. It will create a new communication to send it by post if the email is not read.
        :return: True
        """
        unread_config = self.env.ref(
            "partner_communication_switzerland.child_letter_unread"
        )
        for letter in self:
            if letter.communication_id.filter_not_read():
                self.env["partner.communication.job"].create(
                    {
                        "partner_id": letter.partner_id.id,
                        "config_id": unread_config.id,
                        "object_ids": letter.id,
                    }
                )
        return True

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    def _generate_communication(self, config):
        """
        Generates the communication for given letters.
        :param config_id: partner.communication.config id
        :return: True
        """
        if not self:
            return True

        partner = self.mapped("partner_id")
        auto_send = [l._can_auto_send() for l in self]
        auto_send = reduce(lambda l1, l2: l1 and l2, auto_send)
        comm_vals = {
            "partner_id": partner.id,
            "config_id": config.id,
            "object_ids": self.ids,
            "auto_send": auto_send and partner.email,  # Don't print auto
            "user_id": config.user_id.id,
        }

        if "comm_vals" in self.env.context:
            comm_vals.update(self.env.context["comm_vals"])

        comm_obj = self.env["partner.communication.job"]
        return self.write({"communication_id": comm_obj.create(comm_vals).id})

    def _can_auto_send(self):
        """ Tells if we can automatically send the letter by e-mail or should
        require manual validation before.
        """
        self.ensure_one()
        partner_langs = self.supporter_languages_ids
        types = self.communication_type_ids.mapped("name")
        valid = (
            self.sponsorship_id.state == "active"
            and "Final Letter" not in types
            and "HA" not in self.child_id.local_id
            and "auto" in self.partner_id.letter_delivery_preference
        )
        if not (partner_langs & self.beneficiary_language_ids):
            valid &= self.has_valid_language

        return valid
