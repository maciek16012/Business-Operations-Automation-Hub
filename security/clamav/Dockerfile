FROM clamav/clamav:1.4@sha256:57deb108fc4c72778aa83eafbca7bb7153e28c3f57c005afd38d31f16da86f23
# Resource-limit and encryption alerts must not appear clean to BOAH.
RUN printf '\nAlertExceedsMax yes\nAlertEncrypted yes\nMaxScanTime 10000\nMaxRecursion 10\nMaxFiles 100\nMaxScanSize 20M\nMaxFileSize 5M\nStreamMaxLength 5M\n' >> /etc/clamav/clamd.conf
