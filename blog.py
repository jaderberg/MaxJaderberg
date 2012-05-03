from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import os
from google.appengine.ext.webapp import template
from BeautifulSoup import BeautifulSoup


BLOG_POSTS_DIR = os.path.join(os.path.dirname(__file__), 'blogposts')
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')

NUM_PER_PAGE = 3

class AllPosts(webapp.RequestHandler):
    def get(self):
        blog_template = os.path.join(TEMPLATES_DIR, 'blog.html')

        # Paging
        page = int(self.request.get('page')) if self.request.get('page') else 1

        start = (page - 1) * NUM_PER_PAGE
        stop = start + NUM_PER_PAGE
        posts = os.listdir(BLOG_POSTS_DIR)

        page_post_files = posts[start:stop]

        next_page = (page + 1) if stop < len(posts) else 0
        prev_page = (page - 1) if page > 1 else 0

        posts = []

        for post_file in page_post_files:
            post = {
                'id': post_file.replace('.html', ''),
            }
            # Parse file for soup
            soup = BeautifulSoup(template.render(os.path.join(BLOG_POSTS_DIR, post_file), {}))
            # Get content
            post['content'] = soup.find('div', {'id': 'blogpost'})
            posts.append(post)


        v = {'url' : self.request.url, 'posts': posts, 'next_page': next_page, 'prev_page': prev_page}
        self.response.out.write(template.render(blog_template, v))


class BlogPost(webapp.RequestHandler):
    def get(self, id):

        blog_post_file = os.path.join(BLOG_POSTS_DIR, '%s.html' % id)

        # Check if the post doesnt exist
        if not os.path.exists(blog_post_file):
            self.redirect('/blog/')

        v = {'url': self.request.url}
        self.response.out.write(template.render(blog_post_file, v))


application = webapp.WSGIApplication([
                                        ('/blog/?', AllPosts),
                                        ('/blog/([0-9]+)/?.*', BlogPost),
                                    ], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()