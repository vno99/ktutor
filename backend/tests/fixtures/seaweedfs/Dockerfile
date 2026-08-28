# SeaweedFS image with S3 credentials baked in.
# Avoids the volume-mount / EACCES issues we hit with minio and garage.
#
# Pinned to a specific version (4.44, multi-arch, pushed 6 days ago).
# The official image's ENTRYPOINT is /entrypoint.sh (not /usr/bin/...)
# and the default CMD is `mini -dir=/data`. We override CMD to enable
# the S3 gateway explicitly.
FROM chrislusf/seaweedfs:4.44

# Bake the static S3 config (credentials) into the image. This avoids
# the "container writes root-owned file into host workspace" trap that
# breaks actions/checkout on the next run.
COPY s3config.json /etc/seaweedfs/s3config.json

# Entrypoint: keep the official one (handles permissions, user switching).
# CMD: all-in-one server with the S3 gateway enabled.
# -dir=/data: storage location (ephemeral in CI, that's fine).
# -s3: enable the S3 gateway.
# -s3.port=8333: standard S3 port.
# -s3.config=/etc/seaweedfs/s3config.json: credentials baked above.
# -s3.domainName=localhost: tells SeaweedFS to use "localhost" as the
#   host suffix in the bucket address (matches the S3 endpoint).
ENTRYPOINT ["/entrypoint.sh"]
CMD ["server", "-dir=/data", "-s3", "-s3.port=8333", "-s3.config=/etc/seaweedfs/s3config.json", "-s3.domainName=localhost"]
