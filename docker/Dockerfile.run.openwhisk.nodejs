ARG BASE_IMAGE
FROM $BASE_IMAGE
COPY . /function/
RUN cd /function \
    && npm install --no-package-lock --production \
    && npm cache clean --force
