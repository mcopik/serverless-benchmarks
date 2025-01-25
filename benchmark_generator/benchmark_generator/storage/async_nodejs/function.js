//#test
var result = {};
var config = {
    "entries_number": 1000
};
var number = 0;
var event = {};
//#import
var storage = require('./storage');
var uuid = require('uuid');
var uuidv1 = uuid.v1;
var { Readable } = require("stream")
//#function
function generate_data(entries_number) {
    var dictToFill = {};
    for(var i = 0;i < entries_number;i++) {
        dictToFill[uuidv1()] = uuidv1()
    }
    return dictToFill
}
function streamToPromise(stream) {
    return new Promise(function(resolve, reject) {
      stream.on("close", () =>  {
        resolve();
      });
      stream.on("error", reject);
    })
  }
async function testBucketStorage(dataAsDict, bucket_config) {
    var [client, bucket] = bucket_config;
    var dataAsString = JSON.stringify(dataAsDict);
    var inputStream = Readable.from(dataAsString);
    var result = {};
    var t0 = new Date()
    var [writeStream, uploadPromise, storageKey] = client.uploadStream(bucket, "serverless-benchmark-data.json")
    inputStream.pipe(writeStream)
    await uploadPromise.then(async () => {
        var t1 = new Date()
        read_promise = client.downloadStream(bucket, storageKey)
        await read_promise.then(async (stream) => {
            await (streamToPromise(stream).then((any) => {
                var t2 = new Date();
                result = {
                    "uploaded_to_bucket_bytes": dataAsString.length,
                    "upload_time": t1 - t0,
                    "downloaded_from_bucket_bytes": dataAsString.length,
                    "download_time": t2 - t1,
                    "key": storageKey
                }
            }))
        })
    })
    return result;
}
async function testStorage(entries_number, bucket_config, storage_type) {
    try {
        var data = generate_data(entries_number);
        if(storage_type == "bucket") {
            var res = {}
            await testBucketStorage(data, bucket_config).then((resJson) => res = resJson)
            return res;
        }
        return { "error": "unknown storage"}
    } catch (error) {
        return { "error": error.toString() }
    }
};
//#run
var output_bucket = event.bucket.output;
var entries_number = config.entries_number;
let client = new storage.storage();
var bucket_config = [client, output_bucket];
await testStorage(entries_number, bucket_config, "bucket").then(returnJson => {
    result[number] = returnJson;
  }
);