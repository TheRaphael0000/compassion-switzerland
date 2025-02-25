#    Copyright (C) 2020 Compassion CH
#    @author: Quentin Gigon

from odoo import models, api, fields


class CrowdfundingParticipant(models.Model):
    _name = "crowdfunding.participant"
    _description = "Participant to one of our crowd-fundings"
    _inherit = ["website.seo.metadata", "website.published.multi.mixin", "mail.thread"]
    _inherits = {'utm.source': 'source_id'}
    _order = "project_id desc, name asc"

    project_id = fields.Many2one(
        "crowdfunding.project",
        index=True, ondelete="cascade", string="Project", required=True)
    partner_id = fields.Many2one(
        "res.partner", string="Partner", required=True, index=True, ondelete="cascade"
    )
    personal_motivation = fields.Text(translate=True)
    product_number_goal = fields.Integer(default=0)
    product_number_reached = fields.Integer(compute="_compute_product_number_reached")
    number_sponsorships_goal = fields.Integer(default=0)
    number_sponsorships_reached = fields.Integer(
        compute="_compute_number_sponsorships_reached"
    )
    sponsorship_ids = fields.Many2many(
        "recurring.contract", compute="_compute_sponsorships", string="Sponsorships"
    )
    invoice_line_ids = fields.One2many(
        "account.invoice.line", "crowdfunding_participant_id", string="Donations"
    )
    source_id = fields.Many2one('utm.source', 'UTM Source',
                                required=True, ondelete='cascade')
    facebook_url = fields.Char(string="Facebook link")
    twitter_url = fields.Char(string="Twitter link")
    instagram_url = fields.Char(string="Instagram link")
    personal_web_page_url = fields.Char(string="Personal web page")
    profile_photo = fields.Binary(related="partner_id.image")
    profile_photo_url = fields.Char(compute="_compute_profile_photo_url")
    sponsorship_url = fields.Char(compute="_compute_sponsorship_url")
    is_published = fields.Boolean(related="project_id.is_published", store=True)
    website_id = fields.Many2one("website", related="project_id.website_id", store=True)

    # kanban colors
    color_sponsorship = fields.Char(compute="_compute_color_sponsorship")
    color_product = fields.Char(compute="_compute_color_product")
    color = fields.Integer()

    _sql_constraints = [
        ('registration_unique', "unique(project_id,partner_id)",
         "Only one registration per participant/project is allowed!")
    ]

    @api.model
    def create(self, vals):
        partner = self.env["res.partner"].browse(vals.get("partner_id"))
        project = self.env["crowdfunding.project"].browse(vals.get("project_id"))
        vals["name"] = f"{project.name} - {partner.name}"
        return super().create(vals)

    @api.model
    def get_sponsorship_url(self, participant_id):
        return self.browse(participant_id).sudo().sponsorship_url

    @api.multi
    def _compute_sponsorship_url(self):
        wp = self.env["wordpress.configuration"].sudo().get_config()
        for participant in self:
            utm_medium = "Crowdfunding"
            utm_campaign = participant.project_id.name
            utm_source = participant.name
            participant.sponsorship_url = \
                f"https://{wp.host}{wp.sponsorship_url}?" \
                f"utm_medium={utm_medium}" \
                f"&utm_campaign={utm_campaign}" \
                f"&utm_source={utm_source}"

    @api.multi
    def _compute_product_number_reached(self):
        for participant in self:
            invl = participant.invoice_line_ids.filtered(lambda l: l.state == "paid")
            participant.product_number_reached = int(sum(invl.mapped("quantity")))

    @api.multi
    def _compute_sponsorships(self):
        for participant in self:
            participant.sponsorship_ids = self.env["recurring.contract"].search([
                ("source_id", "=", participant.source_id.id),
                ("type", "like", "S"),
                ("state", "!=", "cancelled")
            ])

    @api.multi
    def _compute_number_sponsorships_reached(self):
        for participant in self:
            participant.number_sponsorships_reached = len(participant.sponsorship_ids)

    @api.multi
    def _compute_profile_photo_url(self):
        domain = self.env['website'].get_current_website()._get_http_domain()
        for participant in self:
            title = participant.sudo().partner_id.title.with_context(lang="en_US")
            if participant.profile_photo:
                path = f"web/content/crowdfunding.participant" \
                    f"/{participant.id}/profile_photo"
            elif title.name == "Mister":
                path = "crowdfunding_compassion/static/src/img/guy.png"
            elif title.name == "Madam":
                path = "crowdfunding_compassion/static/src/img/lady.png"
            else:
                path = None

            participant.profile_photo_url = f"{domain}/{path}" if path else path

    @api.multi
    def _compute_website_url(self):
        for participant in self:
            participant.website_url = f"/participant/{participant.id}"

    def _compute_color_sponsorship(self):
        for project in self:
            if project.number_sponsorships_goal != 0:
                tx_sponsorships = (project.number_sponsorships_reached /
                                   project.number_sponsorships_goal) * 100
                if tx_sponsorships >= 75.0:
                    project.color_sponsorship = 'badge badge-success'
                else:
                    if 50.0 <= tx_sponsorships < 75.0:
                        project.color_sponsorship = 'badge badge-warning'
                    else:
                        project.color_sponsorship = 'badge badge-danger'
            else:
                project.color_sponsorship = 'badge badge-info'

    def _compute_color_product(self):
        for project in self:
            if project.product_number_goal != 0:
                tx_product = (project.product_number_reached /
                              project.product_number_goal) * 100
                if tx_product >= 75.0:
                    project.color_product = 'badge badge-success'
                else:
                    if 50.0 <= tx_product < 75.0:
                        project.color_product = 'badge badge-warning'
                    else:
                        project.color_product = 'badge badge-danger'
            else:
                project.color_product = 'badge badge-info'

    def _default_website_meta(self):
        res = super()._default_website_meta()
        res['default_opengraph']['og:description'] = res[
            'default_twitter']['twitter:description'] = self.personal_motivation
        res['default_opengraph']['og:image'] = res[
            'default_twitter']['twitter:image'] = self.profile_photo_url
        res['default_opengraph']['og:image:secure_url'] = self.profile_photo_url
        res['default_opengraph']['og:image:type'] = "image/jpeg"
        res['default_opengraph']['og:image:width'] = "640"
        res['default_opengraph']['og:image:height'] = "442"
        return res
