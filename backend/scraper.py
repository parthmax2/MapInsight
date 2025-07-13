import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
import random
import re
import os

MAX_SCROLL = 25


class GoogleScraper:
    def __init__(self) -> None:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument("start-maximized")

        self.driver = webdriver.Chrome(options=options)

    def _head_to_reviews(self, url):
        self.driver.get(url)
        try:
            review_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@aria-label, 'Reviews')]")
                )
            )
            review_button.click()
        except Exception as e:
            print(f"[❌] Could not navigate to reviews section: {e}")

    def _get_place_name(self):
        try:
            name_el = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf"))
            )
            return name_el.text.strip().replace(" ", "_")
        except Exception:
            return "GoogleMapsPlace"

    def _sort_newest(self):
        try:
            wait = WebDriverWait(self.driver, 20)
            sort_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@data-value='Sort']")))
            sort_button.click()

            newest_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-index="1"]')))
            newest_button.click()
        except Exception as e:
            print(f"[⚠️] Could not sort reviews by newest: {e}")

    def _scroll(self, max_scrolls=MAX_SCROLL):
        try:
            scrollable_div = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf"))
            )

            last_height = self.driver.execute_script("return arguments[0].scrollHeight", scrollable_div)

            for _ in range(max_scrolls):
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_div)
                time.sleep(random.uniform(1.5, 2.5))
                new_height = self.driver.execute_script("return arguments[0].scrollHeight", scrollable_div)
                if new_height == last_height:
                    break
                last_height = new_height
        except Exception as e:
            print(f"[⚠️] Scroll error: {e}")

    def _expand_reviews(self):
        try:
            buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.w8nwRe.kyuRq")
            for button in buttons:
                try:
                    self.driver.execute_script("arguments[0].click();", button)
                except Exception:
                    continue
        except Exception as e:
            print(f"[⚠️] Expand review error: {e}")

    def _parse(self, review):
        item = {
            "review_id": review.get("data-review-id"),
            "username": review.get("aria-label"),
            "retrieval_date": datetime.now()
        }

        try:
            item["rating"] = float(
                review.find("span", class_="kvMYJc")["aria-label"].split(" ")[0]
            )
        except Exception:
            item["rating"] = None

        try:
            item["relative_date"] = review.find("span", class_="rsqaWe").text
        except Exception:
            item["relative_date"] = None

        try:
            text = review.find("div", class_="MyEned").text
            item["review"] = self._sanitize_string(text)
        except Exception:
            item["review"] = None

        return item

    def _sanitize_string(self, text):
        return (
            text.replace("\r", " ")
            .replace("\n", " ")
            .replace("\t", " ")
            .replace("’", "'")
        )

    def _convert_to_datetime(self, relative):
        now = datetime.now()
        try:
            if "day" in relative:
                days = int(re.search(r"\d+", relative).group())
                return now - pd.Timedelta(days=days)
            if "week" in relative:
                weeks = int(re.search(r"\d+", relative).group())
                return now - pd.Timedelta(weeks=weeks)
            if "month" in relative:
                months = int(re.search(r"\d+", relative).group())
                return now - pd.DateOffset(months=months)
            if "year" in relative:
                years = int(re.search(r"\d+", relative).group())
                return now - pd.DateOffset(years=years)
        except:
            return None
        return now

    def _is_validate_url(self, url):
        return "https://www.google.com/maps/place/" in url

    def scrape_reviews(self, url, num_reviews=10, start_date=None, end_date=None):
        if not self._is_validate_url(url):
            raise ValueError("Invalid Google Maps URL")

        self._head_to_reviews(url)
        self._sort_newest()
        self._scroll()
        self._expand_reviews()

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        reviews_raw = soup.find_all(
            "div",
            attrs={"data-review-id": True, "aria-label": True},
            class_=lambda x: x and "fontBodyMedium" in x,
        )

        if not reviews_raw:
            self._close()
            return {
                "place_name": "Unknown",
                "file_path": "",
                "top_reviews": [{"error": "No reviews found. Try a different link or range."}],
                "map_embed": "https://www.google.com/maps?q=&output=embed"
            }

        parsed = [self._parse(r) for r in reviews_raw]
        for r in parsed:
            r["absolute_date"] = self._convert_to_datetime(r.get("relative_date", ""))

        df = pd.DataFrame(parsed)

        if start_date:
            df = df[df["absolute_date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["absolute_date"] <= pd.to_datetime(end_date)]

        df = df.head(num_reviews).copy()
        df["review_id"] = list(range(1, len(df) + 1))

        place_name = self._get_place_name()
        filename = f"{place_name}_reviews_latest.xlsx"
        filepath = os.path.join("output", filename)
        df.to_excel(filepath, index=False)
        print(f"✅ Saved new Excel: {filepath}")

        # Safe review preview
        if not df.empty and all(col in df.columns for col in ["username", "rating", "review", "absolute_date"]):
            top_10_summary = df[["username", "rating", "review", "absolute_date"]].head(10).to_dict(orient="records")
        else:
            top_10_summary = [{"error": "No valid reviews extracted."}]

        self._close()

        return {
            "place_name": place_name.replace("_", " "),
            "file_path": filepath,
            "top_reviews": top_10_summary,
            "map_embed": url.replace("/place/", "/embed?pb=!1m18!1m12!1m3!")  # rough fallback
        }

    def _close(self):
        try:
            self.driver.quit()
        except Exception as e:
            print(f"[⚠️] Driver close error: {e}")
