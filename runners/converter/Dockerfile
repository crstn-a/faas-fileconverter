FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y \
    pandoc \
    imagemagick \
    ghostscript \
    texlive-xetex \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' \
    /etc/ImageMagick-6/policy.xml

WORKDIR /files

COPY convert.sh /convert.sh

RUN sed -i 's/\r$//' /convert.sh && chmod +x /convert.sh

ENTRYPOINT ["/convert.sh"]