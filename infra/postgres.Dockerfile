# Preserve the existing PostgreSQL 16 Alpine ABI and locale family.
ARG POSTGRES_BASE=postgres:16-alpine
FROM ${POSTGRES_BASE} AS extension
ADD --checksum=sha256:cac0b10c360f05b2d521200105ba3697e773d4cd3731f5a915a7e37ebe0bea85 https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v0.8.7 /tmp/vector.tar.gz
RUN apk add --no-cache build-base && tar -xzf /tmp/vector.tar.gz -C /tmp && cd /tmp/pgvector-0.8.7 && make with_llvm=no OPTFLAGS='' && make with_llvm=no install
FROM ${POSTGRES_BASE}
COPY --from=extension /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/vector.so
COPY --from=extension /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/
