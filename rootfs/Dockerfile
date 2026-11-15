ARG DEBIAN_BASE=debian:trixie-slim
FROM ${DEBIAN_BASE}

ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8

COPY packages.list /tmp/zaod-packages.list
COPY overlay/ /
COPY scripts/finalize-rootfs.sh /usr/local/sbin/zaod-finalize-rootfs
COPY scripts/remove-distro-packages.sh /usr/local/sbin/zaod-remove-distro-packages
COPY packages.list /usr/share/zaod/packages.list

RUN set -eu; \
    apt-get update; \
    sed -e 's/#.*//' -e '/^[[:space:]]*$/d' /tmp/zaod-packages.list \
      | xargs -r apt-get install -y --no-install-recommends; \
    locale-gen en_US.UTF-8; \
    mkdir -p /tmp/zaod-inputs /boot /lib/firmware /usr/share/zaod/licenses; \
    chmod 0755 /usr/local/sbin/zaod-finalize-rootfs /usr/local/sbin/zaod-remove-distro-packages; \
    chmod 0440 /etc/sudoers.d/zaod-admins; \
    chmod 0600 /etc/NetworkManager/system-connections/zaod-wired.nmconnection; \
    visudo -c -f /etc/sudoers; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

CMD ["/usr/local/sbin/zaod-finalize-rootfs"]
