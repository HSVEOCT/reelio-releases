FROM alpine:3.23
RUN apk add --no-cache ca-certificates tzdata postgresql18-client gzip && \
    adduser -D -H -u 10001 reelio && \
    mkdir -p /backups && chown -R reelio:reelio /backups
COPY reelio-api /reelio
COPY THIRD_PARTY_NOTICES.txt /THIRD_PARTY_NOTICES.txt
COPY LICENSE.txt /LICENSE.txt
USER reelio
EXPOSE 8080
ENTRYPOINT ["/reelio"]
