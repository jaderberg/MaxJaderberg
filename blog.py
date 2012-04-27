from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import os

BLOG_POSTS_DIR = os.path.join(os.path.dirname(__file__), 'blogposts')
STATIC_FILES_DIR = os.path.join(os.path.dirname(__file__), 'static')



application = webapp.WSGIApplication([
                                        ('/.*', MainPage)
                                    ], debug=False)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()