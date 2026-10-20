# syntax=docker/dockerfile:1
ARG BASE_IMAGE=debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
FROM ${BASE_IMAGE} AS dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg python3 xz-utils \
    && rm -rf /var/lib/apt/lists/*
COPY xpra.sources /etc/apt/sources.list.d/xpra.sources
# Pin the package authority by its documented primary OpenPGP fingerprint.
RUN curl --fail --location --proto '=https' --tlsv1.2 https://xpra.org/xpra.asc \
      --output /usr/share/keyrings/xpra.asc \
    && gpg --batch --show-keys --with-colons /usr/share/keyrings/xpra.asc \
       | awk -F: '$1 == "fpr" { print $10 }' \
       | grep -Fx B4993B57323148E37977E5D873254CAD17978FAF \
    && chmod 0644 /usr/share/keyrings/xpra.asc \
    && apt-get update && apt-get install -y --no-install-recommends \
    xpra xpra-html5 xvfb openbox dbus-x11 pulseaudio pulseaudio-utils \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    mesa-utils libgl1-mesa-dri libglx-mesa0 libegl-mesa0 libopengl0 mesa-vulkan-drivers \
    libx11-6 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-cursor0 \
    libxrender1 libxi6 libxtst6 libxfixes3 libxrandr2 libxcomposite1 \
    libxcursor1 libxss1 libnss3 libasound2t64 libjack-jackd2-0 libdbus-1-3 \
    libsm6 libice6 libfontconfig1 libgomp1 libvulkan1 libsdl2-2.0-0 \
    fonts-dejavu-core fonts-liberation2 ffmpeg xauth wmctrl xdotool x11-utils x11-xserver-utils \
    && rm -rf /var/lib/apt/lists/*

FROM dependencies AS extracted
COPY prepare.py install_bundles.py /opt/cinematicum/
COPY bundles/ /bundles/
ARG ALLOW_PARTIAL=0
RUN if [ "$ALLOW_PARTIAL" = 1 ]; then \
      python3 /opt/cinematicum/install_bundles.py --allow-partial; \
    else python3 /opt/cinematicum/install_bundles.py; fi

FROM dependencies
ARG APP_UID=1000
ARG APP_GID=1000
RUN if ! getent group "$APP_GID" >/dev/null; then groupadd -g "$APP_GID" cinematicum; fi \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --create-home \
       --home-dir /home/cinematicum --shell /bin/sh cinematicum \
    && mkdir -p /opt/cinematicum /projects /media /run/cinematicum \
    && chown "$APP_UID:$APP_GID" /projects /home/cinematicum
COPY --from=extracted /opt/editors /opt/editors
COPY --from=extracted /opt/cinematicum/installed.json /opt/cinematicum/installed.json
COPY --from=extracted /opt/cinematicum/engines.lock.json /opt/cinematicum/engines.lock.json
COPY supervisor.py control.py /opt/cinematicum/
COPY cinematicum-open cinematicum-control /usr/local/bin/
RUN chmod 0755 /usr/local/bin/cinematicum-open /usr/local/bin/cinematicum-control \
    && dpkg-query -W -f='${Package}\t${Version}\n' > /opt/cinematicum/os-packages.lock
ENV HOME=/home/cinematicum USER=cinematicum DISPLAY=:100 \
    XDG_RUNTIME_DIR=/tmp/cinematicum-runtime \
    DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/cinematicum-runtime/bus \
    QT_X11_NO_MITSHM=1 QT_XCB_GL_INTEGRATION=xcb_glx \
    LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe \
    LANG=C.UTF-8 LC_ALL=C.UTF-8
USER cinematicum
WORKDIR /projects
EXPOSE 14500
ENTRYPOINT ["python3", "/opt/cinematicum/supervisor.py"]
