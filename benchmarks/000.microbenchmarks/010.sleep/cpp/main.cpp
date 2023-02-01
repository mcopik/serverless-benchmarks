
#include <aws/core/Aws.h>
#include <aws/core/utils/json/JsonSerializer.h>
#include <aws/lambda-runtime/runtime.h>

#include <thread>
#include <iostream>

Aws::Utils::Json::JsonValue function(Aws::Utils::Json::JsonView json)
{
  int sleep = json.GetInteger("sleep");

  std::chrono::seconds timespan(sleep);
  std::this_thread::sleep_for(timespan);

  //std::string res_json = "{ \"result\": " + std::to_string(sleep) + "}";
  //return aws::lambda_runtime::invocation_response::success(res_json, "application/json");
  Aws::Utils::Json::JsonValue val;
  val.WithObject("result", std::to_string(sleep));
  return val;
}

