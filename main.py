# Copyright Max Jaderberg 2012
from datetime import timedelta
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import os
from google.appengine.ext.webapp import template
import datetime
from django.utils import simplejson as json
from google.appengine.api.images import Image, JPEG, composite, BOTTOM_CENTER, crop, CENTER_CENTER, TOP_LEFT, BOTTOM_LEFT, BOTTOM_RIGHT, PNG, TOP_RIGHT
from google.appengine.api import memcache, urlfetch
from google.appengine.ext import db
from google.appengine.runtime.apiproxy_errors import RequestTooLargeError
import urllib

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

IG_URL = 'https://api.instagram.com/v1/users/36657960/media/recent?access_token=36657960.1fb234f.5bf801de2cf64301b139b2924a390a42'


class OriginalImage(db.Model):
    image_data = db.BlobProperty()
    date = db.DateTimeProperty(auto_now_add=True)

class BGImage(OriginalImage):
    pass

class ThumbnailImage(OriginalImage):
    pass



class ImagePage(webapp.RequestHandler):
    def get(self):

        resp = urlfetch.fetch(IG_URL)

        data = json.loads(resp.content)

        images = []
        for i, image_object in enumerate(data['data']):
            if i > 10:
                break
            url = image_object['images']['standard_resolution']['url']
            image = {
                'url': url,
                'link': image_object['link'],
                'data': urllib.quote(self.load_image_data(url, OriginalImage).encode('base64')),
            }
            images.append(image)


        self.response.out.write(json.dumps(images))

    def load_image_data(self, url, ImModel):
        key = '%s' % url
        image = ImModel.get_by_key_name(key)
        if image is None:
            response = urlfetch.fetch(url)
            if response.status_code == 200:
                image_data = response.content
                image = ImModel(image_data=image_data, key_name=key)
                image.put()
        return image.image_data

    def send_image_response(self, image_data):
        self.response.headers['Content-Type'] = 'image/jpeg'
        self.response.headers['Cache-Control'] = 'public,max-age=31536000'
        expires_date = datetime.datetime.utcnow() + timedelta(days=365)
        self.response.headers['Expires'] = expires_date.strftime("%d %b %Y %H:%M:%S GMT")
        self.response.out.write(image_data)

urls = [
    (r'/instagram_photos/', ImagePage),
]

application = webapp.WSGIApplication(urls, debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()