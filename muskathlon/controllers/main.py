##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Sebastien Toth <popod@me.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import json
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.website_event_compassion.controllers.events_controller import (
    EventsController,
)

from odoo.http import request, route


class MuskathlonWebsite(EventsController, CustomerPortal):
    @route(
        '/event/<model("crm.event.compassion"):event>/', auth="public", website=True,
        sitemap=EventsController.sitemap_events
    )
    def event_page(self, event, **kwargs):
        result = super(MuskathlonWebsite, self).event_page(event, **kwargs)
        if event.website_muskathlon and result.mimetype == "application/json":
            # The form is in a modal popup and should be returned in JSON
            # and render in the modal (remove full_page option).
            values = json.loads(result.data)
            values["full_page"] = False
            result.data = json.dumps(values)
        return result

    @route(
        '/my/muskathlon/<model("event.registration"):registration>/donations',
        auth="user",
        website=True, sitemap=False
    )
    def my_muskathlon_details(self, registration, **kwargs):
        reports = request.env["muskathlon.report"].search(
            [
                ("user_id", "=", request.env.user.partner_id.id),
                ("event_id", "=", registration.compassion_event_id.id),
            ]
        )
        return request.render("muskathlon.my_details", {"reports": reports})

    @route("/my/muskathlon", type="http", auth="user", website=True)
    def muskathlon_my_account(self, form_id=None, **kw):
        if not request.env.user.partner_id.is_muskathlon:
            return request.redirect("/my/home")

        """ Inject data for forms. """
        values = self._prepare_portal_layout_values()

        partner = values["partner"]
        advocate_details_id = partner.advocate_details_id.id
        registration = partner.registration_ids[:1]
        form_success = False

        # Load forms
        kw["form_model_key"] = "cms.form.muskathlon.trip.information"
        trip_info_form = self.get_form("event.registration", registration.id, **kw)
        if form_id is None or form_id == trip_info_form.form_id:
            trip_info_form.form_process()
            form_success = trip_info_form.form_success

        kw["form_model_key"] = "cms.form.advocate.details"
        about_me_form = self.get_form("advocate.details", advocate_details_id, **kw)
        if form_id is None or form_id == about_me_form.form_id:
            about_me_form.form_process()
            form_success = about_me_form.form_success

        kw["form_model_key"] = "cms.form.muskathlon.passport"
        passport_form = self.get_form("event.registration", registration.id, **kw)
        if form_id is None or form_id == passport_form.form_id:
            passport_form.form_process()
            form_success = passport_form.form_success

        kw["form_model_key"] = "cms.form.muskathlon.flight.details"
        kw["registration_id"] = registration.id
        flight_type = kw.get("flight_type")
        kw["flight_type"] = "outbound"
        flight = registration.flight_ids.filtered(lambda f: f.flight_type == "outbound")
        outbound_flight_form = self.get_form("event.flight", flight.id, **kw)
        if form_id is None or (
                form_id == outbound_flight_form.form_id
                and (not flight_type or flight_type == "outbound")
        ):
            outbound_flight_form.form_process(**kw)
            form_success = outbound_flight_form.form_success
        kw["flight_type"] = "return"
        flight = registration.flight_ids.filtered(lambda f: f.flight_type == "return")
        return_flight_form = self.get_form("event.flight", flight.id, **kw)
        if form_id is None or (
                form_id == return_flight_form.form_id
                and (not flight_type or flight_type == "return")
        ):
            return_flight_form.form_process(**kw)
            form_success = return_flight_form.form_success

        kw["form_model_key"] = "cms.form.group.visit.criminal.record"
        criminal_form = self.get_form("event.registration", registration.id, **kw)
        if form_id is None or form_id == criminal_form.form_id:
            criminal_form.form_process()
            form_success = criminal_form.form_success

        values.update(
            {
                "trip_info_form": trip_info_form,
                "about_me_form": about_me_form,
                "passport_form": passport_form,
                "outbound_flight_form": outbound_flight_form,
                "return_flight_form": return_flight_form,
                "criminal_form": criminal_form,
            }
        )
        values.update(kw)
        if "registrations" not in values.keys():
            registrations_array = []
            for reg in partner.registration_ids:
                registrations_array.append(reg)
            values['registrations'] = registrations_array
        # This fixes an issue that forms fail after first submission
        if form_success:
            result = request.redirect("/my/muskathlon")
        else:
            result = request.render("muskathlon.custom_portal_my_home", values)
        return self._form_redirect(result, full_page=True)

    @route(
        "/muskathlon_registration/payment/validate",
        type="http", auth="public", website=True, sitemap=False
    )
    def registration_payment_validate(self, **post):
        """ Method that should be called by the server when receiving an update
        for a transaction.
        """
        uid = request.env.ref("muskathlon.user_muskathlon_portal").id
        try:
            tx = (
                request.env["payment.transaction"]
                .sudo(uid)
                ._ogone_form_get_tx_from_data(post)
            )
        except ValidationError:
            tx = None

        if not tx or not tx.registration_id:
            return request.render("muskathlon.registration_failure")

        event = tx.registration_id.compassion_event_id
        if tx.state == "done" and tx.registration_id:
            # Confirm the registration
            tx.registration_id.confirm_registration()
        post.update({"event": event})
        return self.compassion_payment_validate(
            tx,
            "muskathlon.new_registration_successful",
            "muskathlon.registration_failure",
            **post
        )

    @route(
        '/my/muskathlon/<model("event.registration"):registration>',
        auth="user", website=True, sitemap=False
    )
    def muskathlon_order_material(self, registration, form_id=None, **kw):
        # Load forms
        kw["form_model_key"] = "cms.form.order.material"
        kw["registration"] = registration
        material_form = self.get_form("crm.lead", **kw)
        if form_id is None or form_id == "order_material":
            material_form.form_process()

        kw["form_model_key"] = "cms.form.order.muskathlon.childpack"
        childpack_form = self.get_form("crm.lead", **kw)
        if form_id is None or form_id == "muskathlon_childpack":
            childpack_form.form_process()

        flyer = "/muskathlon/static/src/img/muskathlon_parrain_example_"
        flyer += request.env.lang[:2] + ".jpg"

        values = {
            "registration": registration,
            "material_form": material_form,
            "childpack_form": childpack_form,
            "flyer_image": flyer,
        }
        return request.render("muskathlon.my_muskathlon_order_material", values)

    @route(
        "/muskathlon_registration/"
        '<int:registration_id>/success',
        type="http", auth="public", website=True, sitemap=False
    )
    def muskathlon_registration_successful(self, registration_id, **kwargs):
        limit_date = datetime.now() - relativedelta(days=1)
        registration = request.env["event.registration"].sudo().browse(registration_id)
        if not registration.exists() or registration.create_date < limit_date:
            return request.redirect("/events")

        values = {
            "registration": registration,
            "event": registration.compassion_event_id,
        }
        return request.render("muskathlon.new_registration_successful_modal", values)

    def get_event_page_values(self, event, **kwargs):
        """
        Gets the values used by the website to render the event page.
        :param event: crm.event.compassion record to render
        :param kwargs: request arguments
        :return: dict: values for the event website template
                       (must contain event, start_date, end_date, form,
                        main_object and website_template values)
        """
        if event.website_muskathlon:
            kwargs["form_model_key"] = "cms.form.event.registration.muskathlon"
        values = super(MuskathlonWebsite, self).get_event_page_values(event, **kwargs)
        if event.website_muskathlon:
            values.update(
                {
                    "disciplines": event.sport_discipline_ids.ids,
                    "website_template": "muskathlon.details",
                }
            )
        return values

    def get_participant_page_values(self, event, registration, **kwargs):
        """
        Gets the values used by the website to render the participant page.
        :param event: crm.event.compassion record to render
        :param registration: event.registration record to render
        :param kwargs: request arguments
        :return: dict: values for the event website template
                       (must contain event, start_date, end_date, form,
                        main_object and website_template values)
        """
        values = super(MuskathlonWebsite, self).get_participant_page_values(
            event, registration, **kwargs
        )
        if event.website_muskathlon:
            values["website_template"] = "muskathlon.participant_details"
        return values

    def get_donation_success_template(self, event):
        if event.website_muskathlon:
            return "muskathlon.donation_successful"
        return super(MuskathlonWebsite, self).get_donation_success_template(event)

    def _prepare_portal_layout_values(self):
        values = super(MuskathlonWebsite, self)._prepare_portal_layout_values()
        if "user" in values:
            partner = values['user'].partner_id
        else:
            partner = request.env.user.partner_id

        registrations = request.env["event.registration"].sudo().search(
            [("partner_id", "=", partner.id)]
        )
        surveys = request.env["survey.user_input"].search(
            [
                (
                    "survey_id",
                    "in",
                    registrations.mapped("event_id.medical_survey_id").ids,
                ),
                ("partner_id", "=", partner.id),
            ]
        )
        surveys_not_started = (
            surveys.filtered(lambda r: r.state == "new") if surveys else False
        )
        survey_not_started = surveys_not_started[0] if surveys_not_started else False
        surveys_done = (
            surveys.filtered(lambda r: r.state == "done") if surveys else False
        )
        survey_already_filled = surveys_done[0] if surveys_done else False

        child_protection_charter = {
            "has_agreed": partner.has_agreed_child_protection_charter,
            "url": "/partner/%s/child-protection-charter?redirect=%s"
                   % (partner.uuid, urllib.parse.quote("/my/home", safe="")),
        }

        if registrations and partner.advocate_details_id:
            values["registrations"] = registrations
        elif registrations:
            values["muskathlete_without_advocate_details"] = True

        values.update(
            {
                "partner": partner,
                "survey_url": request.env.ref("muskathlon.muskathlon_form").public_url,
                "survey_not_started": survey_not_started,
                "survey_already_filled": survey_already_filled,
                "child_protection_charter": child_protection_charter,
            }
        )
        return values
