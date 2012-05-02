from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import os
from google.appengine.ext.webapp import template


BLOG_POSTS_DIR = os.path.join(os.path.dirname(__file__), 'blogposts')
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')

NUM_PER_PAGE = 1

class AllPosts(webapp.RequestHandler):
    def get(self):
        blog_template = os.path.join(TEMPLATES_DIR, 'blog.html')

        page = int(self.request.get('page')) if self.request.get('page') else 1

        start = (page - 1) * NUM_PER_PAGE
        stop = start + NUM_PER_PAGE
        posts = list(reversed(os.listdir(BLOG_POSTS_DIR)))

        page_posts = posts[start:stop]

        next_page = (page + 1) if stop < len(posts) else 0
        prev_page = (page - 1) if page > 1 else 0

        v = {'url' : self.request.url, 'posts': page_posts, 'next_page': next_page, 'prev_page': prev_page}
        self.response.out.write(template.render(blog_template, v))




application = webapp.WSGIApplication([
                                        ('/blog/?', AllPosts)
                                    ], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()