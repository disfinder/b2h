import logging
import argparse
import xml.etree.ElementTree as ET
import datetime as dt
from pathlib import Path
import re
import requests
from requests.adapters import HTTPAdapter, Retry
import shutil
import markdownify

TEMPLATE = '''
---
title: "{title}"
date: "{date}"
categories:
    - blog
tags:
    - imported
---

{content}
'''


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", '--file')
    parser.add_argument("-o", '--out')
    args = parser.parse_args()
    return args


def get_image(url, path, filename):
    logging.debug(f'Getting file {url}...')
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=0.1, )
    s.mount('https://', HTTPAdapter(max_retries=retries))
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        with open(f'{path}/{filename}', 'wb') as thumb:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, thumb)


def process_images(content, path):
    links_matcher = re.compile('\[!\[\]\(.*?\)\]\(.*?\)')  # match an image link inside a markdown
    urls_matcher = re.compile('\(https:.*?\)')  # match a thumbnail and original image inside of an image link

    images = links_matcher.findall(content)
    for index, image in enumerate(images):
        logging.debug(f'Processing image {index:03d} out of {len(images)}')
        urls = urls_matcher.findall(image)
        if len(urls) != 2:  # we only care about images with thumbnails
            logging.error(f'Malformed url for image: {image}')
            continue
        assert len(urls) == 2
        mini_url = urls[0][1:-1]  # strip braces
        max_url = urls[1][1:-1]
        logging.debug(f'Getting file {mini_url}...')
        filename = f'thumb_{index:02d}.jpg'
        get_image(mini_url, path, filename)
        content = content.replace(mini_url, filename)

        filename = f'img{index:02d}.jpg'
        get_image(max_url, path, filename)
        content = content.replace(max_url, filename)
    return content


def main():
    args = parse_args()
    tree = ET.parse(args.file)
    # gosh this XML/atom parser is horrible
    all_objects = [dict((attr.tag, attr.text) for attr in el) for el in tree.getroot()]

    posts = [post for post in all_objects  # want to skip comments, drafts and such
             if post and (post['{http://schemas.google.com/blogger/2018}type'] == 'POST') and
             post['{http://schemas.google.com/blogger/2018}status'] == 'LIVE'
             ]
    logging.debug(f'All objects count: {len(all_objects)}, posts count:{len(posts)}')
    for index, post in enumerate(posts):
        logging.debug(f'Processing post {index:02d} out of {len(posts)}')
        post['date'] = dt.datetime.fromisoformat(post['{http://www.w3.org/2005/Atom}published'])
        if args.out:
            date = dt.datetime.fromisoformat(post['{http://www.w3.org/2005/Atom}published'])
            dirname = f"{args.out}/{date.year}/{date.month:02d}/{date.day:02d}"
            Path(dirname).mkdir(parents=True, exist_ok=True)

            out_filename = f"{dirname}/index.md"
            with open(out_filename, 'w') as out_file:
                original_content = post['{http://www.w3.org/2005/Atom}content']
                if original_content is None:
                    original_content = ''
                markdown_content = markdownify.markdownify(original_content, heading_style="ATX")
                markdown_content = process_images(markdown_content, dirname) # download images locally

                if post['{http://www.w3.org/2005/Atom}title']:
                    title = post['{http://www.w3.org/2005/Atom}title'].replace('"', '\\"')
                else:
                    title = ''
                content = TEMPLATE.format(
                    title=title,
                    date=post['{http://www.w3.org/2005/Atom}published'],
                    content=markdown_content,
                )
                logging.debug(f'writing file {out_filename}')
                out_file.write(content)
        else:
            print(post['{http://www.w3.org/2005/Atom}title'])


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
