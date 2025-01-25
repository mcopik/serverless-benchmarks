//#test
var config = {
  "size_in_bytes": 10485760
};
var result = {};
var number = 0;
//#import
var math = require('mathjs');
//#function
const testMemory = async (size) => {
  var t0 = new Date().getTime(); // Get current time in milliseconds
  var a = math.ones([Math.floor(size / 8)]); // Ensure size is an integer
  var t1 = new Date().getTime(); // Get current time in milliseconds
  
  return {
    "time": t1 - t0,
    "size_in_bytes": size
  };
};
//#run
var array_size_in_bytes = config["size_in_bytes"];
testMemory(array_size_in_bytes).then(returnJson => {
    result[number] = returnJson;
    console.log(result); // Output the result
});
