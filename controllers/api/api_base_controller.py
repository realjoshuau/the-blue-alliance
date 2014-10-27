import json
import logging
import md5
import tba_config
import urllib
import uuid
import webapp2

from google.appengine.api import urlfetch
from google.appengine.ext import deferred
from google.appengine.ext import ndb

from controllers.base_controller import CacheableHandler
from datafeeds.parser_base import ParserInputException
from helpers.validation_helper import ValidationHelper
from models.api_auth_access import ApiAuthAccess
from models.cached_response import CachedResponse
from models.sitevar import Sitevar


# used for deferred call
def track_call(api_action, api_label, x_tba_app_id):
    """
    For more information about GAnalytics Protocol Parameters, visit
    https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
    """
    analytics_id = Sitevar.get_by_id("google_analytics.id")
    if analytics_id is None:
        logging.warning("Missing sitevar: google_analytics.id. Can't track API usage.")
    else:
        GOOGLE_ANALYTICS_ID = analytics_id.contents['GOOGLE_ANALYTICS_ID']
        params = urllib.urlencode({
            'v': 1,
            'tid': GOOGLE_ANALYTICS_ID,
            'cid': uuid.uuid3(uuid.NAMESPACE_X500, str(x_tba_app_id)),
            't': 'event',
            'ec': 'api-v02',
            'ea': api_action,
            'el': api_label,
            'cd1': x_tba_app_id,  # custom dimension 1
            'ni': 1,
            'sc': 'end',  # forces tracking session to end
        })

        analytics_url = 'http://www.google-analytics.com/collect?%s' % params
        urlfetch.fetch(
            url=analytics_url,
            method=urlfetch.GET,
            deadline=10,
        )


class ApiBaseController(CacheableHandler):

    API_VERSION = 1

    def __init__(self, *args, **kw):
        super(ApiBaseController, self).__init__(*args, **kw)
        self.response.headers['content-type'] = 'application/json; charset="utf-8"'
        self.response.headers['Access-Control-Allow-Origin'] = '*'

    def handle_exception(self, exception, debug):
        """
        Handle an HTTP exception and actually writeout a
        response.
        Called by webapp when abort() is called, stops code excution.
        """
        logging.info(exception)
        if isinstance(exception, webapp2.HTTPException):
            self.response.set_status(exception.code)
            self.response.out.write(self._errors)
        else:
            self.response.set_status(500)

    def get(self, *args, **kw):
        self._validate_tba_app_id()
        self._errors = ValidationHelper.validate(self._validators)
        if self._errors:
            self.abort(400)

        self._track_call(*args, **kw)
        super(ApiBaseController, self).get(*args, **kw)
        self.response.headers['X-TBA-Version'] = self.API_VERSION
        self._set_cache_header_length(self.CACHE_HEADER_LENGTH)

    def _read_cache(self):
        """
        Overrides parent method to use CachedResponse instead of memcache
        Returns:
        None if not cached
        the cached response if cached
        True if in not modified
        """
        response = CachedResponse.get_by_id(self.cache_key)
        if response:
            if self._has_been_modified_since(response.updated):
                response.headers['Last-Modified'] = self.response.headers['Last-Modified']
                return response
            else:
                return True
        else:
            return None

    def _write_cache(self, response):
        """
        Overrides parent method to use CachedResponse instead of memcache
        """
        if tba_config.CONFIG["response_cache"]:
            CachedResponse(
                id=self.cache_key,
                headers_json=json.dumps(dict(response.headers)),
                body=response.body,
            ).put()

    @classmethod
    def delete_cache_multi(cls, cache_keys):
        """
        Overrides parent method to use CachedResponse instead of memcache
        """
        logging.info("Deleting cache keys: {}".format(cache_keys))
        ndb.delete_multi([ndb.Key(CachedResponse, cache_key) for cache_key in cache_keys])

    def _track_call_defer(self, api_action, api_label):
        deferred.defer(track_call, api_action, api_label, self.x_tba_app_id, _queue="api-track-call")

    def _validate_tba_app_id(self):
        """
        Tests the presence of a X-TBA-App-Id header or URL param.
        """
        self.x_tba_app_id = self.request.headers.get("X-TBA-App-Id")
        if self.x_tba_app_id is None:
            self.x_tba_app_id = self.request.get('X-TBA-App-Id')

        logging.info("X-TBA-App-Id: {}".format(self.x_tba_app_id))
        if not self.x_tba_app_id:
            self._errors = json.dumps({"Error": "X-TBA-App-Id is a required header or URL param. Please see http://www.thebluealliance.com/apidocs for more info."})
            self.abort(400)

        x_tba_app_id_parts = self.x_tba_app_id.split(':')

        if len(x_tba_app_id_parts) != 3 or any(len(part) == 0 for part in x_tba_app_id_parts):
            self._errors = json.dumps({"Error": "X-TBA-App-Id must follow a specific format. Please see http://www.thebluealliance.com/apidocs for more info."})
            self.abort(400)

    def _set_cache_header_length(self, seconds):
        if type(seconds) is not int:
            logging.error("Cache-Control max-age is not integer: {}".format(seconds))
            return

        self.response.headers['Cache-Control'] = "public, max-age=%d" % max(seconds, 61)  # needs to be at least 61 seconds to work
        self.response.headers['Pragma'] = 'Public'


class ApiTrustedBaseController(webapp2.RequestHandler):
    def __init__(self, *args, **kw):
        super(ApiTrustedBaseController, self).__init__(*args, **kw)
        self.response.headers['content-type'] = 'application/json; charset="utf-8"'

    def handle_exception(self, exception, debug):
        """
        Handle an HTTP exception and actually writeout a
        response.
        Called by webapp when abort() is called, stops code excution.
        """
        logging.info(exception)
        if isinstance(exception, webapp2.HTTPException):
            self.response.set_status(exception.code)
            self.response.out.write(self._errors)
        else:
            self.response.set_status(500)

    def post(self, event_key):
        auth_id = self.request.headers.get('X-TBA-Auth-Id')
        if not auth_id:
            self._errors = json.dumps({"Error": "Must provide a request header parameter 'X-TBA-Auth-Id'"})
            self.abort(400)

        auth_sig = self.request.headers.get('X-TBA-Auth-Sig')
        if not auth_sig:
            self._errors = json.dumps({"Error": "Must provide a request header parameter 'X-TBA-Auth-Sig'"})
            self.abort(400)

        auth = ApiAuthAccess.get_by_id(auth_id)
        if not auth or md5.new('{}{}{}'.format(auth.secret, self.request.path, self.request.body)).hexdigest() != auth_sig:
            self._errors = json.dumps({"Error": "Invalid X-TBA-Auth-Id and/or X-TBA-Auth-Sig!"})
            self.abort(400)

        allowed_event_keys = [ekey.id() for ekey in auth.event_list]
        if event_key not in allowed_event_keys:
            self._errors = json.dumps({"Error": "Only allowed to edit events: {}".format(', '.join(allowed_event_keys))})
            self.abort(400)

        try:
            self._process_request(self.request, event_key)
        except ParserInputException, e:
            self._errors = json.dumps({"Error": e.message})
            self.abort(400)
