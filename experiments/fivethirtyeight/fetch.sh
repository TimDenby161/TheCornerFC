#!/bin/sh
# FiveThirtyEight's final club forecasts file (CC BY 4.0), from the Internet Archive: ABC took the
# site down in March 2025 and its old address now answers with a web page. This capture is the
# last one, with the same content digest as the copy taken on 25 June 2023.
set -e
cd "$(dirname "$0")"
curl -sL -o spi_matches.csv \
  "https://web.archive.org/web/20250306125411id_/https://projects.fivethirtyeight.com/soccer-api/club/spi_matches.csv"
echo "75fcee0f06f18c854b775437f7a0f36b06249e0f3b6a607d94e34ab6d84815f4  spi_matches.csv" | shasum -a 256 -c
