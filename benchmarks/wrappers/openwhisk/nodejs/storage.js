
const minio = require('minio'),
  uuid = require('uuid'),
  util = require('util'),
  stream = require('stream'),
  fs = require('fs');

class minio_storage {

  constructor() {
    let minioConfig = JSON.parse(fs.readFileSync('/function/minioConfig.json'));
    let address = minioConfig["url"];
    let access_key = minioConfig["access_key"];
    let secret_key = minioConfig["secret_key"];

    this.client = new minio.Client(
      {
        endPoint: address.split(':')[0],
        port: parseInt(address.split(':')[1], 10),
        accessKey: access_key,
        secretKey: secret_key,
        useSSL: false
      }
    );
  }

  unique_name(file) {
    let [name, extension] = file.split('.');
    let uuid_name = uuid.v4().split('-')[0];
    return util.format('%s.%s.%s', name, uuid_name, extension);
  }

  upload(bucket, file, filepath) {
    let uniqueName = this.unique_name(file);
    return [uniqueName, this.client.fPutObject(bucket, uniqueName, filepath)];
  };

  download(bucket, file, filepath) {
    return this.client.fGetObject(bucket, file, filepath);
  };

  uploadStream(bucket, file) {
    var write_stream = new stream.PassThrough();
    let uniqueName = this.unique_name(file);
    let promise = this.client.putObject(bucket, uniqueName, write_stream, write_stream.size);
    return [write_stream, promise, uniqueName];
  };

  downloadStream(bucket, file) {
    var read_stream = new stream.PassThrough();
    return this.client.getObject(bucket, file);
  };

  static get_instance() {
    if(!this.instance) {
      this.instance = new storage();
    }
    return this.instance;
  }


};
exports.storage = minio_storage;
