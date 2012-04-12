# Copyright Max Jaderberg 2012
from datetime import datetime, timedelta
import hashlib
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import os
from google.appengine.ext.webapp import template
from django.utils import simplejson as json
from google.appengine.api.images import Image, JPEG, composite, BOTTOM_CENTER, crop, CENTER_CENTER, TOP_LEFT, BOTTOM_LEFT, BOTTOM_RIGHT, PNG, TOP_RIGHT
from google.appengine.api import memcache, urlfetch
from google.appengine.ext import db
from google.appengine.runtime.apiproxy_errors import RequestTooLargeError
import math

BASE_URL = 'http://www.trickedouttimeline.com'

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

TEAR_KEY = 'tear'
ZOOM_KEY = 'zoom'
PUZZLE_KEY = 'puzzle'

COVER_PHOTO_DIMS = (850, 315)
BOTTOM_MARGIN = 38.0
P_PHOTO_LEFT_MARGIN = 27.0
P_PHOTO_HEIGHT = 125.0

P_PHOTO_MIN_WIDTH = 180

# with respect to cover photo bottom left corner
P_PHOTO_CENTER = (P_PHOTO_LEFT_MARGIN + P_PHOTO_HEIGHT/2.0, 92.0 - 5.0 - P_PHOTO_HEIGHT/2.0)

MAX_MEMCACHE_SIZE = 1000000

THUMB_WIDTH = 450

USE_MEMCACHE = False

WATERMARK_KEY = 'watermark2'


class TempImage(db.Model):
    image_data = db.BlobProperty()
    date = db.DateTimeProperty(auto_now_add=True)

class ImageMachine(object):

    def resize_width(self, image_data, width, quality=100, output_encoding=JPEG):
        img = Image(image_data=image_data)
        img.resize(width=width)
        return img.execute_transforms(output_encoding=output_encoding, quality=quality)

    def add_watermark(self, img):
        # Get the watermark
        w_img = memcache.get(WATERMARK_KEY)
        if w_img is None:
            f = open('watermark.png')
            w_img = f.read()
            memcache.add(WATERMARK_KEY, w_img)
            f.close()
        return composite([(img, 0, 0, 1.0, TOP_RIGHT), (w_img, 0, -13, 1.0, TOP_RIGHT)], COVER_PHOTO_DIMS[0], COVER_PHOTO_DIMS[1], output_encoding=JPEG, quality=100)


    def get_image_from_url(self, url):
        key = 'url-image'
        image_data = self.get_cached(url, key=key)
        if image_data is None:
            fetch_url = url
            response = urlfetch.fetch(fetch_url)
            if response.status_code == 200:
                image_data = response.content
                I.set_cached(url, image_data, key=key)
        return image_data

    def get_cache_key(self, id, key):
        return '%s:%s' % (key, id)


    def get_cached(self, id, key='image'):
        if USE_MEMCACHE:
            return memcache.get(self.get_cache_key(id, key))
        else:
            img = TempImage.get_by_key_name(self.get_cache_key(id, key))
            if img is None:
                return None
            else:
                return img.image_data

    def set_cached(self, id, image_data, key='image', cache_hours=0.1):
        if USE_MEMCACHE:
            # Cache for 6 mins by default
            return memcache.add(self.get_cache_key(id, key), image_data, cache_hours * 60 * 60)
        else:
            img = TempImage(image_data=image_data, key_name=self.get_cache_key(id, key))
            try:
                return img.put()
            except RequestTooLargeError:
                image_data = I.resize_width(image_data, COVER_PHOTO_DIMS[1])
                img = TempImage(image_data=image_data, key_name=self.get_cache_key(id, key))
                return img.put()

    def send_image_response(self, response, image_data):
        response.headers['Content-Type'] = 'image/jpeg'
        response.headers['Cache-Control'] = 'public,max-age=31536000'
        expires_date = datetime.utcnow() + timedelta(days=0)
        response.headers['Expires'] = expires_date.strftime("%d %b %Y %H:%M:%S GMT")
        response.out.write(image_data)

    def send_image_download_response(self, response, image_data, filename="download.jpg"):
        response.headers['Content-Disposition'] = 'attachment;filename=%s' % filename
        self.send_image_response(response, image_data)

I = ImageMachine()


class Effect(object):
    name = None
    effect_urls = None


class EffectPage(webapp.RequestHandler):

    def _parse_coords(self, bg_img_width, thumb_width):

        scale_factor = float(float(bg_img_width)/float(thumb_width))

#        Crop to selection
        try:
            left = scale_factor*float(self.request.get('coords[x]'))
        except ValueError:
            left = 0.0
        try:
            right = scale_factor*float(self.request.get('coords[x2]'))
        except ValueError:
            right = 0.0
        try:
            top = scale_factor*float(self.request.get('coords[y]'))
        except ValueError:
            top = 0.0
        try:
            bottom = scale_factor*float(self.request.get('coords[y2]'))
        except ValueError:
            bottom = 0.0

        return {
            'left': left,
            'right': right,
            'top': top,
            'bottom': bottom,
        }

class StaticPage(webapp.RequestHandler):
    template_file = None

    def get(self):
        this_template = os.path.join(TEMPLATE_DIR, self.template_file)
        template_values = {'url' : self.request.url, 'base_url': BASE_URL}
        self.response.out.write(template.render(this_template, template_values))

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=--=--=-=-=-=-=-=-=-=-
# PAGES
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=--=--=-=-=-=-=-=-=-=-

class ImagePage(webapp.RequestHandler):

    def get(self, download, filename, id):
#        Grab the image from cache
        response_img = I.get_cached(id)
#        Send the image back
        if download == 'download':
            I.send_image_download_response(self.response, response_img, filename='%s.jpg' % filename)
        else:
            I.send_image_response(self.response, response_img)

class TermsPage(StaticPage):
    template_file = 'terms.html'

class MainPage(StaticPage):
    template_file = 'home.html'


class GenericUploadPage(webapp.RequestHandler):
    name = None

    def get(self):
        effect = self.name
        self.response.headers['Content-Type'] = 'application/javascript'

        t = os.path.join(TEMPLATE_DIR, effect, 'upload_bubble.html')
        c = {
            'effect': effect
        }

        self.response.out.write(json.dumps({
            'success': True,
            'html': template.render(t, c)
        }))

    def post(self):
        """
        When the user uploads a photo
        """
        effect = self.name
        self.response.headers['Content-Type'] = 'text/html'

        fb_url = self.request.get("fb_url")
        img = self.request.get("img")

        # if we don't have image data we'll quit now
        if not img and not fb_url:
            self.response.out.write(json.dumps({'success': False, 'message':"No image selected!"}))
            return

        # get image from url if that option selected
        if fb_url:
            img = I.get_image_from_url(fb_url)

#        Generate an ID (BEFORE RESIZING)
        id = hashlib.sha224(img).hexdigest()

#        Grab the original image from cache
        response_img = I.get_cached(id)

        if response_img is None:
#           test resize to make sure it is an image
            try:
                test_resize = I.resize_width(img, COVER_PHOTO_DIMS[0])
            except Exception, exc:
                return  self.response.out.write(json.dumps({'success': False, 'message':"File is not an image!", 'exc': exc.message}))
#            check if image is too big to put in cache without resizing
            img_byte_size = len(img)

            if img_byte_size > MAX_MEMCACHE_SIZE:
#                resize to fit in memcache
                scale = float(float(MAX_MEMCACHE_SIZE)/float(img_byte_size))
                img = I.resize_width(img, int(Image(image_data=img).width*scale*0.99))
            try:
                I.set_cached(id, img)
            except Exception:
#                Generally due to too big file (it should be small enough)
                img = I.resize_width(img, int(Image(image_data=img).width*0.8))
                I.set_cached(id, img)

        self.response.out.write(json.dumps({'success': True,
                                            'id': id,
        }))

class GenericCropPage(webapp.RequestHandler):
    name = None
    
    def get(self, id):
        effect = self.name
        self.response.headers['Content-Type'] = 'application/javascript'

        # Create thumbnail
        img = I.get_cached(id)
        response_img = I.resize_width(img, THUMB_WIDTH)
        thumb_id = hashlib.sha224(response_img).hexdigest()
        I.set_cached(thumb_id, response_img)

        t = os.path.join(TEMPLATE_DIR, effect, 'crop_bubble.html')
        c = {
            'effect': effect,
            'id': id,
            'crop_image': '/image/thumb/%s' % thumb_id
        }

        self.response.out.write(json.dumps({
            'success': True,
            'html': template.render(t, c)
        }))





class TearEffect(Effect):
    name = 'tear'

    class TearUploadPage(GenericUploadPage):
        name = 'tear'

    class TearCropPage(GenericCropPage):
        name = 'tear'

    class TearEffectPage(EffectPage):
        name = 'tear'
        
        def get(self, id):
            self.response.headers['Content-Type'] = 'application/javascript'
            preview = self.request.get('preview')

            # Get the tear
            tear_img = memcache.get(TEAR_KEY)
            if tear_img is None:
                f = open('tear.png')
                tear_img = f.read()
                memcache.add(TEAR_KEY, tear_img)
                f.close()

            # Get the background image
            bg_img_data = I.get_cached(id)
            if bg_img_data is None:
                self.response.out.write(json.dumps({'success': False, 'message': 'You took too long, start again!'}))
                return
            bg_img = Image(image_data=bg_img_data)

            # Crop to selection
            coords = self._parse_coords(bg_img.width, THUMB_WIDTH)
            right_x = float(coords['right']/float(bg_img.width)) if float(coords['right']/float(bg_img.width)) < 1.0 else 1.0
            bottom_y = float(coords['bottom']/float(bg_img.height)) if float(coords['bottom']/float(bg_img.height)) < 1.0 else 1.0
            right_x = right_x if right_x > 0.0 else 0.0
            bottom_y = bottom_y if bottom_y > 0.0 else 0.0
            try:
                bg_img_data = crop(bg_img_data, float(coords['left']/float(bg_img.width)), float(coords['top']/float(bg_img.height)), right_x, bottom_y, output_encoding=JPEG, quality=100)
            except Exception:
                self.response.out.write(json.dumps({'success': False, 'message': 'Invalid image!'}))
                return

    #        Resize to cover photo size
            bg_img_data = I.resize_width(bg_img_data, COVER_PHOTO_DIMS[0])

            if bg_img_data is None:
                self.response.out.write(json.dumps({'success': False, 'message': 'Invalid image!'}))
                return

    #        Overlay the tear at the bottom of the background image
            cover_img = composite([(bg_img_data, 0, 0, 1.0, BOTTOM_CENTER), (tear_img, 0, 0, 1.0, BOTTOM_CENTER)], COVER_PHOTO_DIMS[0], COVER_PHOTO_DIMS[1], output_encoding=JPEG, quality=100)


            prev_id = id = ''
            if not preview:
                cover_img = I.add_watermark(cover_img)
                id = hashlib.sha224(cover_img).hexdigest()
                I.set_cached(id, cover_img)
                t = os.path.join(TEMPLATE_DIR, self.name, 'download_bubble.html')
                c = {
                    'coverurl': '/download/torn_cover/%s' % id,
                    'effect': self.name,
                }
                html = template.render(t, c)
            else:
    #           Create preview image
                prev_cover_img = I.resize_width(cover_img, 300)
                prev_id = hashlib.sha224(prev_cover_img).hexdigest()
                I.set_cached(prev_id, prev_cover_img, cache_hours=0.01)
                html = None

            self.response.out.write(json.dumps({
                'success': True,
                'prev_cover_url': '/image/preview_cover/%s' % prev_id,
                'html': html,
            }))

    effect_urls = [
        (r'/%s/upload' % name, TearUploadPage),
        (r'/%s/crop/([a-f0-9]+)' % name, TearCropPage),
        (r'/%s/([a-f0-9]+)' % name, TearEffectPage),
    ]

class TwoForOneEffect(Effect):
    name = '2for1'

    class TfOUploadPage(GenericUploadPage):
        name = '2for1'

    class TfOCropPage(GenericCropPage):
        name = '2for1'

    class TfOEffectPage(EffectPage):
        name = '2for1'

        def get(self, id):

            self.response.headers['Content-Type'] = 'application/javascript'

            preview = self.request.get('preview')

    #        Get the background image
            bg_img_data = I.get_cached(id)
            if bg_img_data is None:
                self.response.out.write(json.dumps({'success': False, 'message': 'You took too long, start again!'}))
                return
            original_bg_img = Image(image_data=bg_img_data)

    #        use this as template http://smashinghub.com/wp-content/uploads/2012/01/wanna-create-your-own.png
    #        first cut the cover photo - bottom of whole image is the bottom of the profile picture

            coords = self._parse_coords(original_bg_img.width, THUMB_WIDTH)

            right_x = float(coords['right']/float(original_bg_img.width)) if float(coords['right']/float(original_bg_img.width)) < 1.0 else 1.0
            bottom_y = float(coords['bottom']/float(original_bg_img.height)) if float(coords['bottom']/float(original_bg_img.height)) < 1.0 else 1.0
            right_x = right_x if right_x > 0.0 else 0.0
            bottom_y = bottom_y if bottom_y > 0.0 else 0.0
            try:
                bg_img_data = crop(bg_img_data, float(coords['left']/float(original_bg_img.width)), float(coords['top']/float(original_bg_img.height)), right_x, bottom_y, output_encoding=JPEG, quality=100)
            except Exception:
                self.response.out.write(json.dumps({'success': False, 'message': 'Invalid image!'}))
                return

            original_bg_img = Image(image_data=bg_img_data)

            scaled_bg_img_data = I.resize_width(bg_img_data, COVER_PHOTO_DIMS[0])
            scaled_bg_img = Image(image_data=scaled_bg_img_data)

            cover_img_data = crop(scaled_bg_img_data, 0.0, 0.0, 1.0, float(float(scaled_bg_img.height-38)/float(scaled_bg_img.height)), output_encoding=JPEG, quality=100)

            cover_id = ''
            if not preview:
                cover_img_data = I.add_watermark(cover_img_data)
                cover_id = hashlib.sha224(cover_img_data).hexdigest()
                I.set_cached(cover_id, cover_img_data)

    #        Now make the profile photo

            if original_bg_img.width < COVER_PHOTO_DIMS[0]:
    #            uploaded image is smaller so use the resized one
                bg_img_data = scaled_bg_img_data
                original_bg_img = scaled_bg_img

            scale = float(float(original_bg_img.width)/float(COVER_PHOTO_DIMS[0])) #scaling to fb profile size

            left = scale*P_PHOTO_LEFT_MARGIN
            right = scale*(left + P_PHOTO_HEIGHT)
            top = original_bg_img.height - scale*P_PHOTO_HEIGHT

            profile_photo_img = crop(bg_img_data, float(float(left)/float(original_bg_img.width)), float(float(top)/float(original_bg_img.height)), float(float(right)/float(original_bg_img.width)), 1.0, output_encoding=JPEG, quality=100)

            if Image(image_data=profile_photo_img).width < P_PHOTO_MIN_WIDTH:
                profile_photo_img = I.resize_width(profile_photo_img, P_PHOTO_MIN_WIDTH)

            profile_id = ''
            if not preview:
                profile_id = hashlib.sha224(profile_photo_img).hexdigest()
                I.set_cached(profile_id, profile_photo_img)

    #        Create preview images
            prev_cover_id = prev_profile_id = ''
            if preview:
                prev_cover_img = I.resize_width(cover_img_data, 300)
                prev_cover_id = hashlib.sha224(prev_cover_img).hexdigest()
                I.set_cached(prev_cover_id, prev_cover_img, cache_hours=0.01)
                prev_profile_img = I.resize_width(profile_photo_img, 44)
                prev_profile_id = hashlib.sha224(prev_profile_img).hexdigest()
                I.set_cached(prev_profile_id, prev_profile_img, cache_hours=0.01)
                html = None
            else:
                t = os.path.join(TEMPLATE_DIR, self.name, 'download_bubble.html')
                c = {
                    'coverurl': '/download/2for1_cover/%s' % cover_id,
                    'profileurl': '/download/2for1_profile/%s' % profile_id,
                    'effect': self.name,
                }
                html = template.render(t, c)


            self.response.out.write(json.dumps({
                'success': True,
                'html': html,
                'prev_cover_url': '/image/preview_cover/%s' % prev_cover_id,
                'prev_profile_url': '/image/preview_profile/%s' % prev_profile_id,
            }))

    effect_urls = [
        (r'/%s/upload' % name, TfOUploadPage),
        (r'/%s/crop/([a-f0-9]+)' % name, TfOCropPage),
        (r'/%s/([a-f0-9]+)' % name, TfOEffectPage),
    ]

class ZoomEffect(Effect):
    name = 'zoom'

    class ZoomUploadPage(GenericUploadPage):
        name = 'zoom'

    class ZoomCropPage(GenericCropPage):
        name = 'zoom'

    class ZoomEffectPage(EffectPage):
        name = 'zoom'

        def get(self, id):

            self.response.headers['Content-Type'] = 'application/javascript'

            preview = self.request.get('preview')

            # Get the profile image
            img_data = I.get_cached(id)
            if img_data is None:
                self.response.out.write(json.dumps({'success': False, 'message': 'You took too long, start again!'}))
                return
            original_img = Image(image_data=img_data)

            # Crop to profile picture
            coords = self._parse_coords(original_img.width, THUMB_WIDTH)

            right_x = float(coords['right']/float(original_img.width)) if float(coords['right']/float(original_img.width)) < 1.0 else 1.0
            bottom_y = float(coords['bottom']/float(original_img.height)) if float(coords['bottom']/float(original_img.height)) < 1.0 else 1.0
            right_x = right_x if right_x > 0.0 else 0.0
            bottom_y = bottom_y if bottom_y > 0.0 else 0.0
            try:
                profile_photo_img = crop(img_data, float(coords['left']/float(original_img.width)), float(coords['top']/float(original_img.height)), right_x, bottom_y, output_encoding=JPEG, quality=100)
            except Exception:
                self.response.out.write(json.dumps({'success': False, 'message': 'Invalid image!'}))
                return

            # now assemble the cover photo, biggest zoom first
            bw = 2000.0
            bb = float(bw)/2.0
            bt = bb - COVER_PHOTO_DIMS[1]
            bl = float(bw/2.0 - P_PHOTO_CENTER[0])
            br = float(bl + COVER_PHOTO_DIMS[0])
            cover_photo_img = I.resize_width(profile_photo_img, int(bw))
            cover_photo_img = crop(cover_photo_img, bl/bw, bt/bw, br/bw, bb/bw, output_encoding=JPEG, quality=100)
            for i in reversed(range(3)):
                zoom_w = float((2**(i+1))*P_PHOTO_HEIGHT)
                # zoom the profile pic
                zoomed_profile_img = I.resize_width(profile_photo_img, int(zoom_w))
                # load the frame
                frame_key = '%s_%s' % (ZOOM_KEY, str(i+1))
                frame_img = memcache.get(frame_key)
                if frame_img is None:
                    f = open('%s.png' % frame_key)
                    frame_img = f.read()
                    memcache.add(frame_key, frame_img)
                    f.close()
                frame_image = Image(image_data=frame_img)
                # place the zoomed image on the frame
                zoomed_profile_img = composite([(frame_img, 0, 0, 1.0, CENTER_CENTER), (zoomed_profile_img, 0, 0, 1.0, CENTER_CENTER)], frame_image.width, frame_image.height, color=0, output_encoding=JPEG, quality=100)
                # compose on to the cover photo
                cover_photo_img = composite([(cover_photo_img, 0, 0, 1.0, CENTER_CENTER),(zoomed_profile_img, int(P_PHOTO_CENTER[0]-COVER_PHOTO_DIMS[0]/2), int(COVER_PHOTO_DIMS[1]/2-P_PHOTO_CENTER[1]), 1.0, CENTER_CENTER)], COVER_PHOTO_DIMS[0], COVER_PHOTO_DIMS[1], color=0, output_encoding=JPEG, quality=100)
            

            prev_cover_id = prev_profile_id = ''
            if preview:
                prev_cover_img = I.resize_width(cover_photo_img, 300)
                prev_cover_id = hashlib.sha224(prev_cover_img).hexdigest()
                I.set_cached(prev_cover_id, prev_cover_img, cache_hours=0.01)
                prev_profile_img = I.resize_width(profile_photo_img, 44)
                prev_profile_id = hashlib.sha224(prev_profile_img).hexdigest()
                I.set_cached(prev_profile_id, prev_profile_img, cache_hours=0.01)
                html = None
            else:
                cover_photo_img = I.add_watermark(cover_photo_img)
                profile_id = hashlib.sha224(profile_photo_img).hexdigest()
                I.set_cached(profile_id, profile_photo_img)
                cover_id = hashlib.sha224(cover_photo_img).hexdigest()
                I.set_cached(cover_id, cover_photo_img)
                t = os.path.join(TEMPLATE_DIR, self.name, 'download_bubble.html')
                c = {
                    'coverurl': '/download/zoom_cover/%s' % cover_id,
                    'profileurl': '/download/zoom_profile/%s' % profile_id,
                    'effect': self.name,
                }
                html = template.render(t, c)

            self.response.out.write(json.dumps({
                'success': True,
                'html': html,
                'prev_cover_url': '/image/preview_cover/%s' % prev_cover_id,
                'prev_profile_url': '/image/preview_profile/%s' % prev_profile_id,
            }))

    effect_urls = [
        (r'/%s/upload' % name, ZoomUploadPage),
        (r'/%s/crop/([a-f0-9]+)' % name, ZoomCropPage),
        (r'/%s/([a-f0-9]+)' % name, ZoomEffectPage),
    ]

class PuzzleEffect(object):
    name = 'puzzle'

    class PuzzleUploadPage(GenericUploadPage):
        name = 'puzzle'

    class PuzzleCoverCropPage(webapp.RequestHandler):
        name = 'puzzle'

        def get(self, id):
            effect = self.name
            self.response.headers['Content-Type'] = 'application/javascript'

            # Create thumbnail
            img = I.get_cached(id)
            response_img = I.resize_width(img, THUMB_WIDTH)
            thumb_id = hashlib.sha224(response_img).hexdigest()
            I.set_cached(thumb_id, response_img)

            t = os.path.join(TEMPLATE_DIR, effect, 'cover_crop_bubble.html')
            c = {
                'effect': effect,
                'id': id,
                'crop_image': '/image/thumb/%s' % thumb_id
            }

            self.response.out.write(json.dumps({
                'success': True,
                'html': template.render(t, c)
            }))

    class PuzzleProfileCropPage(EffectPage):
        name = 'puzzle'

        def get(self, id):
            effect = self.name
            self.response.headers['Content-Type'] = 'application/javascript'
            preview = self.request.get('preview')

            # Get the background image
            bg_img_data = I.get_cached(id)
            if bg_img_data is None:
                self.response.out.write(json.dumps({'success': False, 'message': 'You took too long, start again!'}))
                return
            bg_img = Image(image_data=bg_img_data)

            # Crop to selection
            coords = self._parse_coords(bg_img.width, THUMB_WIDTH)
            right_x = float(coords['right']/float(bg_img.width)) if float(coords['right']/float(bg_img.width)) < 1.0 else 1.0
            bottom_y = float(coords['bottom']/float(bg_img.height)) if float(coords['bottom']/float(bg_img.height)) < 1.0 else 1.0
            right_x = right_x if right_x > 0.0 else 0.0
            bottom_y = bottom_y if bottom_y > 0.0 else 0.0
            try:
                bg_img_data = crop(bg_img_data, float(coords['left']/float(bg_img.width)), float(coords['top']/float(bg_img.height)), right_x, bottom_y, output_encoding=JPEG, quality=100)
            except Exception:
                self.response.out.write(json.dumps({'success': False, 'message': 'Invalid image!'}))
                return

    #        Resize to cover photo size
            bg_img_data = I.resize_width(bg_img_data, COVER_PHOTO_DIMS[0])

            if bg_img_data is None:
                self.response.out.write(json.dumps({'success': False, 'message': 'Invalid image!'}))
                return


            prev_id = ''
            if not preview:
                cover_id = hashlib.sha224(bg_img_data).hexdigest()
                I.set_cached(cover_id, bg_img_data)
                # Create thumbnail
                response_img = I.resize_width(bg_img_data, THUMB_WIDTH)
                thumb_id = hashlib.sha224(response_img).hexdigest()
                I.set_cached(thumb_id, response_img)

                t = os.path.join(TEMPLATE_DIR, effect, 'profile_crop_bubble.html')
                c = {
                    'effect': effect,
                    'id': cover_id,
                    'crop_image': '/image/thumb/%s' % thumb_id,
                }
                html = template.render(t, c)
            else:
    #           Create preview image
                prev_cover_img = I.resize_width(bg_img_data, 300)
                prev_id = hashlib.sha224(prev_cover_img).hexdigest()
                I.set_cached(prev_id, prev_cover_img, cache_hours=0.01)
                html = None

            self.response.out.write(json.dumps({
                'success': True,
                'prev_cover_url': '/image/preview_cover/%s' % prev_id,
                'html': html,
            }))

    class PuzzleEffectPage(EffectPage):
        name = 'puzzle'

        def get(self, id):
            self.response.headers['Content-Type'] = 'application/javascript'
            preview = self.request.get('preview')

            # Get the profile image
            bg_img_data = I.get_cached(id)
            if bg_img_data is None:
                self.response.out.write(json.dumps({'success': False, 'message': 'You took too long, start again!'}))
                return
            bg_img = Image(image_data=bg_img_data)

            # Get profile picture image
            coords = self._parse_coords(bg_img.width, THUMB_WIDTH)

            right_x = float(coords['right']/float(bg_img.width)) if float(coords['right']/float(bg_img.width)) < 1.0 else 1.0
            bottom_y = float(coords['bottom']/float(bg_img.height)) if float(coords['bottom']/float(bg_img.height)) < 1.0 else 1.0
            right_x = right_x if right_x > 0.0 else 0.0
            bottom_y = bottom_y if bottom_y > 0.0 else 0.0
            try:
                profile_photo_img = crop(bg_img_data, float(coords['left']/float(bg_img.width)), float(coords['top']/float(bg_img.height)), right_x, bottom_y, output_encoding=JPEG, quality=100)
            except Exception:
                self.response.out.write(json.dumps({'success': False, 'message': 'Invalid image!'}))
                return

            # Apply puzzle to cover photo
            # Get the puzzle board
            board_img = memcache.get('puzzle_cover')
            if board_img is None:
                f = open('puzzle_cover.png')
                board_img = f.read()
                memcache.add('puzzle_cover', board_img)
                f.close()

            bg_img_data = composite([(bg_img_data, 0, 0, 1.0, CENTER_CENTER),(board_img, int(coords['left']+133), int(coords['bottom']+40), 1.0, BOTTOM_RIGHT)], COVER_PHOTO_DIMS[0], COVER_PHOTO_DIMS[1], output_encoding=JPEG, quality=100)

            # Apply the mask to the profile photo
            # Get the puzzle piece
            piece_img_data = memcache.get('puzzle_profile')
            if piece_img_data is None:
                f = open('puzzle_profile.png')
                piece_img_data = f.read()
                memcache.add('puzzle_profile', piece_img_data)
                f.close()
            piece_img = Image(image_data=piece_img_data)
            profile_photo_img = I.resize_width(profile_photo_img, piece_img.width)

            profile_photo_img = composite([(profile_photo_img, 0, 0, 1.0, CENTER_CENTER),(piece_img_data, 0, 0, 1.0, CENTER_CENTER)], piece_img.width, piece_img.height, output_encoding=JPEG, color=1, quality=100)

            profile_photo_img = I.resize_width(profile_photo_img, 182)

            prev_cover_id = prev_profile_id = ''
            if preview:
                prev_cover_img = I.resize_width(bg_img_data, 300)
                prev_cover_id = hashlib.sha224(prev_cover_img).hexdigest()
                I.set_cached(prev_cover_id, prev_cover_img, cache_hours=0.01)
                prev_profile_img = I.resize_width(profile_photo_img, 44)
                prev_profile_id = hashlib.sha224(prev_profile_img).hexdigest()
                I.set_cached(prev_profile_id, prev_profile_img, cache_hours=0.01)
                html = None
            else:
                bg_img_data = I.add_watermark(bg_img_data)
                profile_id = hashlib.sha224(profile_photo_img).hexdigest()
                I.set_cached(profile_id, profile_photo_img)
                cover_id = hashlib.sha224(bg_img_data).hexdigest()
                I.set_cached(cover_id, bg_img_data)
                t = os.path.join(TEMPLATE_DIR, self.name, 'download_bubble.html')
                c = {
                    'coverurl': '/download/puzzle_cover/%s' % cover_id,
                    'profileurl': '/download/puzzle_profile/%s' % profile_id,
                    'effect': self.name,
                }
                html = template.render(t, c)

            self.response.out.write(json.dumps({
                'success': True,
                'html': html,
                'prev_cover_url': '/image/preview_cover/%s' % prev_cover_id,
                'prev_profile_url': '/image/preview_profile/%s' % prev_profile_id,
            }))

    effect_urls = [
        (r'/%s/upload' % name, PuzzleUploadPage),
        (r'/%s/crop/cover/([a-f0-9]+)' % name, PuzzleCoverCropPage),
        (r'/%s/crop/profile/([a-f0-9]+)' % name, PuzzleProfileCropPage),
        (r'/%s/([a-f0-9]+)' % name, PuzzleEffectPage),
    ]

class TimewarpEffect(Effect):
    name = 'timewarp'

    class TimewarpUploadPage(GenericUploadPage):
        name = 'timewarp'

    class TimewarpCropPage(GenericCropPage):
        name = 'timewarp'

    class TimewarpEffectPage(EffectPage):
        name = 'timewarp'

        def get(self, id):
            self.response.headers['Content-Type'] = 'application/javascript'
            preview = self.request.get('preview')

            # Get the blue background
            blue_img = memcache.get('blue_cover')
            if blue_img is None:
                f = open('blue_cover.png')
                blue_img = f.read()
                memcache.add('blue_cover', blue_img)
                f.close()

            # Get the profile photo frames
            frame_img = memcache.get('zoom_1')
            if frame_img is None:
                f = open('zoom_1.png')
                frame_img = f.read()
                memcache.add('zoom_1', frame_img)
                f.close()

            # get images to use
            a = b = c = d = e = f =g = None
            images = self.request.get('profile_photos')
            images = [a, b, c, d, e, f, g]
            num_images = len(images)

            # profile photo center wrt bottom left corner
            p_photo_x = [125.0, 32.0]
            vanishing_x = [750.0, 310.0]
            final_width = 5.0
            start_width = 135.0
            start_p_width = 125.0
            final_p_width = 4.0
            x_steps = (vanishing_x[0] - p_photo_x[0])/num_images
            y_steps = (vanishing_x[1] - p_photo_x[1])/num_images
            grad = (vanishing_x[1] - p_photo_x[1])/(vanishing_x[0] - p_photo_x[0])
            width_steps = (start_width - final_width)/num_images
            p_width_steps = (start_p_width - final_p_width)/num_images

            cover_image = blue_img

            for i in reversed(range(1, num_images+1)):
                x = p_photo_x[0] + i*(x_steps-0.1*i)
                y = p_photo_x[1] + i*(y_steps-0.1*i)
                frame_width = max(start_width - i*(width_steps-0.0*i), 1)
                image = I.resize_width(frame_img, int(frame_width))
                if images[i-1] is not None:
                    p_image = I.get_cached(images[i-1])
                    p_image = I.resize_width(p_image, int(max(start_p_width - i*(p_width_steps-0.0*i), 1)))
                    image = composite([(frame_img, 0, 0, 1.0, CENTER_CENTER), (p_image, 0, 0, 1.0, CENTER_CENTER)], int(frame_width), int(frame_width), color=0, output_encoding=JPEG, quality=100)
                else:
                    pass
                cover_image = composite([(cover_image, 0, 0 , 1.0, BOTTOM_LEFT), (image, int(x), int(-y), 1.0, BOTTOM_LEFT)], COVER_PHOTO_DIMS[0], COVER_PHOTO_DIMS[1], color=0, output_encoding=JPEG, quality=100)

            I.send_image_response(self.response, cover_image)

            

    effect_urls = [
        (r'/%s/upload' % name, TimewarpUploadPage),
        (r'/%s/crop/([a-f0-9]+)' % name, TimewarpCropPage),
        (r'/%s/([a-f0-9]+)' % name, TimewarpEffectPage),
    ]

# ADD THE EFFECT CLASSES TO THIS ARRAY FOR URL GENERATION
effects = [TearEffect, TwoForOneEffect, ZoomEffect, PuzzleEffect, TimewarpEffect]

urls = [(r'/(image|download)/([0-9a-z_]+)/([a-f0-9]+)', ImagePage),]

for e in effects:
    urls.extend(e.effect_urls)

urls.extend([
    (r'/terms', TermsPage),
    (r'.*', MainPage)
])

application = webapp.WSGIApplication(urls, debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()