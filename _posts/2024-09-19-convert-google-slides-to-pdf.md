---
layout: post
title: "Convert Google Slides to PDF"
date: 2024-09-19
description: "How to convert Google Slides to PDF? Well, just open Google Slides, then click in menu File -&gt;..."
tags:
  - googleslides
  - pdf
  - converter
canonical_url: "https://dev.to/jkrajniak/convert-google-slides-to-pdf-2jkd"
---

How to convert Google Slides to PDF? Well, just open Google Slides, then click in menu **File -> Downdload -> PDF Document**. That's all ;)

---

This sounds easy, but what if you cannot open the slides in Google Slides? What if you only have the embedded interface, the one that is created when you click **File -> Share -> Publish** to web? In fact, there is no easy solution. You cannot print; it just results in a blank, white page. There is also no download option from the interface.

![Example of the interface of embeded slides](/assets/images/posts/convert-google-slides-to-pdf/291aef2a1b.png)

In this short article, I will show you how to solve this problem by using a simple Python script.

## Ingredients

If we cannot download the PDF from the slides or print it, we can still take screenshots ;) The only thing is that we don't want to do this manually. Instead, we'll just use the tool that is used to perform tests - [Selenium](https://selenium-python.readthedocs.io/).

Selenium is a tool that allows you to automate your web application tests. It uses webdrivers, which are headless versions of web browsers. The interactions with the web, like clicking, inputting text, etc., are coded using e.g., Python or other supported languages. Here, I will use Python.

## Code

The main function is `convert_slides_to_png`, which takes the URL as input and stores the screenshots in the specified directory.

```python
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from argparse import ArgumentParser


def convert_slides_to_png(url: str, file_prefix: str, output_dir: str):
    service = Service('/usr/local/bin/chromedriver')  # Replace with the actual path
    options = Options()
    options.add_argument("--disable-search-engine-choice-screen")
    options.add_argument("--headless=new")  # Run in headless mode (no visible browser window)
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1492, 1119)
    driver.get(url)  # Replace with your desired URL

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

    # Find the element to hide (replace with your element locator)
    driver.execute_script("""
        var elements = document.querySelectorAll('.punch-viewer-navbar');
        for (var i = 0; i < elements.length; i++) {
            elements[i].style.display = 'none';
        }
    """)

    def get_page_from_url(url: str) -> int:
        params = url.split('?')[1]
        params = params.split('=')
        page_id = int(params[1].split('.')[1].replace('p', ''))
        return page_id


    body_element = driver.find_element(By.TAG_NAME, 'body')
    body_element.send_keys(Keys.END)

    new_url = driver.current_url
    end_page_num = get_page_from_url(new_url)

    body_element.send_keys(Keys.HOME)

    for i in range(0, end_page_num):
        file_path = f'{output_dir}/{file_prefix}_page_{i}.png'
        driver.save_screenshot(file_path)
        print(f'Page {i} of {end_page_num} saved to {file_path}')
        body_element.send_keys(Keys.ARROW_RIGHT)
        
    print('Done')
```
Here, we actually don't click on the prev/next buttons; instead, we simulate pressing keys (HOME, ARROW_RIGHT, END) to interact with the Google Slides interface.

Let's just add a simple CLI, and we are ready to get the screenshots.

```python
def main():
    parser = ArgumentParser(description='Convert Google Slides to PNG')
    parser.add_argument('--url-file', type=str, help='File with urls of the Google Slides')
    parser.add_argument('--output-dir', type=str, default='slides', help='Output directory')
    args = parser.parse_args()
    
    with open(args.url_file, 'r') as f:
        urls = f.readlines()
        print(f'Processing {len(urls)} urls')
        for url in urls:
            print(f'Processing {url}')
            url, file_prefix = url.strip().split(',')
            convert_slides_to_png(url, file_prefix, args.output_dir)
```

The list of slides is provided as a CSV file with columns: `url` and `file_prefix`.

```
https://docs.google.com/presentation/d/1rTqxnE6_IrTVF8xjYz_ejdrFWbgdjCJgVLD34PVgifw/embed;presentation1
```

To run the script, you need to 
```sh
$ python3 cli.py --url-file urls.txt --output-dir slides
```

This will read URLs from `urls.txt` and output slides to `slides/`, where each slide page will be prefixed by presentation1.

---

Happy scrapping!

---

If you liked the post, then you can [buy me a coffee](https://www.buymeacoffee.com/jkrajniak). Thanks in advance.