
#include <memory>

#include <aws/core/auth/AWSCredentialsProvider.h>
#include <aws/core/client/ClientConfiguration.h>
#include <aws/dynamodb/model/AttributeDefinition.h>
#include <aws/dynamodb/model/GetItemRequest.h>
#include <aws/dynamodb/model/PutItemRequest.h>
#include <aws/dynamodb/model/PutItemResult.h>

#include <boost/interprocess/streams/bufferstream.hpp>

#include "key-value.hpp"
#include "utils.hpp"

KeyValue::KeyValue()
{
  Aws::Client::ClientConfiguration config;
  //config.region = "eu-central-1";
  config.caFile = "/etc/pki/tls/certs/ca-bundle.crt";

  char const TAG[] = "LAMBDA_ALLOC";
  auto credentialsProvider = Aws::MakeShared<Aws::Auth::EnvironmentAWSCredentialsProvider>(TAG);
  _client.reset(new Aws::DynamoDB::DynamoDBClient(credentialsProvider, config));
}

uint64_t KeyValue::download_file(Aws::String const &table, Aws::String const &key,
                        int &required_retries, double& read_units, bool with_backoff)
{
  Aws::DynamoDB::Model::GetItemRequest req;

  // Set up the request
  req.SetTableName(table);
  req.SetReturnConsumedCapacity(Aws::DynamoDB::Model::ReturnConsumedCapacity::TOTAL);
  Aws::DynamoDB::Model::AttributeValue hashKey;
  hashKey.SetS(key);
  req.AddKey("key", hashKey);
    
  auto bef = timeSinceEpochMillisec();
  int retries = 0;
  const int MAX_RETRIES = 1500;

  while (retries < MAX_RETRIES) {
    auto get_result = _client->GetItem(req);
    if (get_result.IsSuccess()) {

      // Reference the retrieved fields/values
      auto result = get_result.GetResult();
      const Aws::Map<Aws::String, Aws::DynamoDB::Model::AttributeValue>& item = result.GetItem();
      if (item.size() > 0) {
          uint64_t finishedTime = timeSinceEpochMillisec();

          required_retries = retries;
          // GetReadCapacityUnits returns 0?
          read_units = result.GetConsumedCapacity().GetCapacityUnits();

          return finishedTime - bef;
      }

    } else {
      retries += 1;
      if(with_backoff) {
        int sleep_time = retries;
        if (retries > 100) {
            sleep_time = retries * 2;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(sleep_time));
      }
    }
  }
  return 0;
}

uint64_t KeyValue::upload_file(Aws::String const &table,
                        Aws::String const &key,
                        double& write_units,
                        int size, unsigned char* pBuf)
{
  Aws::Utils::ByteBuffer buf(pBuf, size);

  Aws::DynamoDB::Model::PutItemRequest req;
  req.SetTableName(table);
  req.SetReturnConsumedCapacity(Aws::DynamoDB::Model::ReturnConsumedCapacity::TOTAL);

  Aws::DynamoDB::Model::AttributeValue av;
  av.SetB(buf);
  req.AddItem("data", av);
  av.SetS(key);
  req.AddItem("key", av);

  uint64_t bef = timeSinceEpochMillisec();
  const Aws::DynamoDB::Model::PutItemOutcome put_result = _client->PutItem(req);
  if (!put_result.IsSuccess()) {
      std::cout << put_result.GetError().GetMessage() << std::endl;
      return 1;
  }
  auto result = put_result.GetResult();
  // GetWriteCapacityUnits returns 0?
  write_units = result.GetConsumedCapacity().GetCapacityUnits();
  uint64_t finishedTime = timeSinceEpochMillisec();

  return finishedTime - bef;
}
