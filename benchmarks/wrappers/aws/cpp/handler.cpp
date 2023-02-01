
#include <aws/core/Aws.h>
#include <aws/lambda-runtime/runtime.h>
#include <aws/s3/S3Client.h>

#include <boost/uuid/uuid.hpp>
#include <boost/uuid/uuid_generators.hpp>
#include <boost/uuid/uuid_io.hpp>

#include "utils.hpp"

// Global variables that are retained across function invocations
bool cold_execution = true;
std::string container_id = "";
std::string cold_start_var = "";

Aws::Utils::Json::JsonValue function(Aws::Utils::Json::JsonView req);

aws::lambda_runtime::invocation_response handler(aws::lambda_runtime::invocation_request const &req)
{
  Aws::Utils::Json::JsonValue json(req.payload);
  Aws::Utils::Json::JsonView json_view = json.View();
  // HTTP trigger with API Gateaway sends payload as a serialized JSON
  // stored under key 'body' in the main JSON
  // The SDK trigger converts everything for us
  if(json_view.ValueExists("body")){
    Aws::Utils::Json::JsonValue parsed_body{json_view.GetString("body")};
    json = std::move(parsed_body);
    json_view = json.View();
  }

  const auto begin = std::chrono::system_clock::now();
  auto ret = function(json.View());
  const auto end = std::chrono::system_clock::now();

  Aws::Utils::Json::JsonValue body;
  body.WithObject("result", ret);

  // Switch cold execution after the first one.
  if(cold_execution)
    cold_execution = false;

  auto b = std::chrono::duration_cast<std::chrono::microseconds>(begin.time_since_epoch()).count() / 1000.0 / 1000.0;
  auto e = std::chrono::duration_cast<std::chrono::microseconds>(end.time_since_epoch()).count() / 1000.0 / 1000.0;
  body.WithDouble("begin", b);
  body.WithDouble("end", e);
  body.WithDouble("results_time", e - b);
  body.WithString("request_id", req.request_id);
  body.WithBool("is_cold", cold_execution);
  body.WithString("container_id", container_id);
  body.WithString("cold_start_var", cold_start_var);

  Aws::Utils::Json::JsonValue final_result;
  final_result.WithObject("body", body);
  return aws::lambda_runtime::invocation_response::success(final_result.View().WriteReadable(), "application/json");
}

int main()
{
  Aws::SDKOptions options;
  Aws::InitAPI(options);

  const char * cold_var = std::getenv("cold_start");
  if(cold_var)
    cold_start_var = cold_var;
  container_id = boost::uuids::to_string(boost::uuids::random_generator()());

  aws::lambda_runtime::run_handler(handler);

  Aws::ShutdownAPI(options);
  return 0;
}

