##############################################################################
#
#    Copyright (C) 2016 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from datetime import datetime, timedelta
from enum import Enum

from odoo import models, fields, api


COLOR_MAPPING = {
    "invited": 0,
    "confirmed": 10,
    "declined": 1,
    "attended": 11
}


class ZoomCommunication(Enum):
    REGISTRATION = "partner_communication_switzerland.config_onboarding_zoom_registration_confirmation"
    LINK = "partner_communication_switzerland.config_onboarding_zoom_link"
    REMINDER = "partner_communication_switzerland.config_onboarding_zoom_reminder"


class ZoomAttendee(models.Model):
    _name = "res.partner.zoom.attendee"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Zoom Attendee"
    _rec_name = "partner_id"
    _order = "id desc"

    partner_id = fields.Many2one("res.partner", "Partner", required=True, index=True)
    zoom_session_id = fields.Many2one(
        "res.partner.zoom.session", "Zoom session", required=True, index=True, ondelete="cascade")
    state = fields.Selection([
        ("invited", "Invited"),
        ("confirmed", "Confirmed"),
        ("attended", "Attended"),
        ("declined", "Declined")
    ], default="invited", group_expand="_expand_states")
    optional_message = fields.Text()
    color = fields.Integer(compute="_compute_color")

    link_received = fields.Boolean(default=False)

    _sql_constraints = [
        ("unique_participant", "unique(partner_id,zoom_session_id)",
         "This partner is already invited to this zoom session!")
    ]

    def _compute_color(self):
        for attendee in self:
            attendee.color = COLOR_MAPPING.get(attendee.state)

    def _expand_states(self, states, domain, order):
        return [key for key, val in type(self).state.selection]

    def inform_about_next_session(self):
        for attendee in self:
            next_zoom = attendee.zoom_session_id.get_next_session()
            if next_zoom:
                next_zoom.add_participant(attendee.partner_id)
            else:
                # Notify the staff
                lang = attendee.partner_id.lang[:2]
                user_id = self.env["res.config.settings"].get_param(
                    f"zoom_attendee_{lang}_id")
                if user_id:
                    attendee.activity_schedule(
                        "mail.mail_activity_data_todo",
                        summary="Sponsor wants to attend the next Zoom session",
                        note="This person is not available for the upcoming zoom with "
                             "new sponsors, but wants to attend the next one. No "
                             "following session was found, please add him to "
                             "participants once it's created.",
                        user_id=user_id)

    def notify_user(self):
        self.ensure_one()
        lang = self.partner_id.lang[:2]
        user_id = self.env["res.config.settings"].get_param(
            f"zoom_attendee_{lang}_id")
        if user_id:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary="Participant registered for the zoom session",
                note=self.optional_message,
                user_id=user_id)

    def send_communication(self, config_name):
        config_id = self.env.ref(config_name.value).id
        partner_id = self.partner_id.id

        # avoid sending this twice communication
        if config_name == ZoomCommunication.LINK:
            if self.link_received:
                return
            else:
                self.link_received = True

        if config_name in [ZoomCommunication.REMINDER, ZoomCommunication.LINK]:
            object_id = self.zoom_session_id.id
        elif config_name in [ZoomCommunication.REGISTRATION]:
            object_id = self.id
        else:
            object_id = None

        return self.env["partner.communication.job"].create({
            "config_id": config_id,
            "partner_id": partner_id,
            "object_ids": object_id,
        })

    @api.one
    def form_completion_callback(self):
        if datetime.now() > self.zoom_session_id.date_send_link:
            return self.send_communication(ZoomCommunication.LINK)
        return self.send_communication(ZoomCommunication.REGISTRATION)

