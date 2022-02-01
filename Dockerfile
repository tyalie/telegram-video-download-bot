FROM python:3.9

# see https://github.com/yt-dlp/FFmpeg-Builds/releases
ARG FFMPEG_URL=https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz
ENV ffmpeg_url=${FFMPEG_URL}

# install ffmpeg
WORKDIR /tmp/cache
RUN ffmpeg=${ffmpeg_url##*/} \
  && wget "${ffmpeg_url}" \
  && tar xvf "${ffmpeg}" \
  && cp ${ffmpeg%.tar.xz}/bin/* /bin/ \
  && rm -rf /tmp/cache


WORKDIR /opt/app

# install requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src/main.py"]
