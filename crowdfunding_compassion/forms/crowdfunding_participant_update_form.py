##############################################################################
#
#    Copyright (C) 2020 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, fields, _
from odoo.http import request

from odoo.addons.website_compassion.tools.image_compression import compress_big_images

class CrowdfundingParticipatUpdateForm(models.AbstractModel):
    _name = "cms.form.crowdfunding.participant.update"
    _inherit = "cms.form"

    form_buttons_template = "cms_form_compassion.modal_form_buttons"
    form_id = "modal_crowdfunding_participant_update"
    _form_model = "crowdfunding.participant"
    _form_model_fields = [
        "personal_motivation",
        "facebook_url",
        "twitter_url",
        "instagram_url",
        "personal_web_page_url",
    ]

    profile_photo = fields.Binary()

    @property
    def _form_fieldsets(self):
        fieldset = [{
            "id": "project",
            "title": _("Your project"),
            "fields": [
                "profile_photo",
                "personal_motivation",
            ],
        },
            {
                "id": "social_medias",
                "title": _("Social Medias"),
                "fields": [
                    "facebook_url",
                    "twitter_url",
                    "instagram_url",
                    "personal_web_page_url",
                ],
            }]
        return fieldset

    @property
    def form_title(self):
        return _("Your project")

    @property
    def submit_text(self):
        return _("Save")

    @property
    def form_widgets(self):
        res = super().form_widgets
        res.update({
            "profile_photo": "cms_form_compassion.form.widget.simple.image"
        })
        return res

    def _form_write(self, values):
        """Just write on the main object. Use sudo."""
        participant = self.main_object
        if "personal_motivation" in values:
            # Write the description in all languages
            participant.with_context(lang="en_US").personal_motivation = values[
                "personal_motivation"]
            participant.with_context(lang="fr_CH").personal_motivation = values[
                "personal_motivation"]
            participant.with_context(lang="de_DE").personal_motivation = values[
                "personal_motivation"]
            participant.with_context(lang="it_IT").personal_motivation = values[
                "personal_motivation"]
        participant.write(values.copy())

    def form_cancel_url(self, main_object=None):
        return request.redirect("/my/together")

    @property
    def form_msg_success_updated(self):
        return _("Project updated.")

    def form_before_create_or_update(self, values, extra_values):
        """ Dismiss any pending status message, to avoid multiple
        messages when multiple forms are present on same page.
        """
        if extra_values.get("profile_photo"):
            self.main_object.partner_id.image = compress_big_images(extra_values["profile_photo"])
        self.o_request.website.get_status_message()
