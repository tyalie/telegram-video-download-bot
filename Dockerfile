FROM python:3.9

ENV ffmpeg=ffmpeg-master-latest-linux64-gpl.tar.xz

# install ffmpeg
WORKDIR /tmp/cache
RUN wget "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/${ffmpeg}" \
  && tar xvf "${ffmpeg}" \
  && cp ${ffmpeg%.tar.xz}/bin/* /bin/ \
  && rm -rf /tmp/cache


WORKDIR /opt/app

# install requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src/main.py"]
