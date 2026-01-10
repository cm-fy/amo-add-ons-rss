# amo-add-ons-rss

This repository automatically generates and publishes an RSS feed of the latest AMO (addons.mozilla.org) add-ons using GitHub Actions and GitHub Pages.

## Live Feed

Once GitHub Pages is enabled, your feed will be available at:

https://cm-fy.github.io/amo-add-ons-rss/amo_latest_addons.xml

## How it works

- The workflow runs every 6 hours (or on manual trigger).
- It runs the Python script to fetch and generate the RSS feed.
- The resulting XML is published to the repository and served via GitHub Pages.

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the script:
   ```bash
   python generate_amo_rss_Version2.py
   ```

## Automation

See `.github/workflows/generate-rss.yml` for workflow details.

## GitHub Pages Setup

1. Go to your repository Settings > Pages.
2. Set the source to the `gh-pages` branch, root folder.
3. The feed will be available at the URL above.
