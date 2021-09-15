const path = require('path'), fs = require('fs');

async function main(args) {
  var func = require('/function/function.js');
  var begin = Date.now() / 1000;
  var start = process.hrtime();
  var ret = await func.handler(args);
  var elapsed = process.hrtime(start);
  var end = Date.now() / 1000;
  var micro = elapsed[1] / 1e3 + elapsed[0] * 1e6;
  var is_cold = false;
  var fname = path.join('/tmp', 'cold_run');
  if (!fs.existsSync(fname)) {
    is_cold = true;
    fs.closeSync(fs.openSync(fname, 'w'));
  }

  return {
    begin: begin,
    end: end,
    compute_time: micro,
    results_time: 0,
    result: ret,
    request_id: process.env.__OW_ACTIVATION_ID,
    is_cold: is_cold,
  };
}

exports.main = main;
