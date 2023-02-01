
#include <cstdint>
#include <string>
#include <initializer_list>
#include <memory>

#include <aws/core/utils/memory/stl/AWSString.h>
#include <aws/dynamodb/DynamoDBClient.h>

class KeyValue
{
  // non-copyable, non-movable
  std::shared_ptr<Aws::DynamoDB::DynamoDBClient> _client;
public:

  KeyValue();

uint64_t download_file(Aws::String const &bucket,
                        Aws::String const &key,
                        int& required_retries,
                        double& read_units,
                        bool with_backoff = false);

uint64_t upload_file(Aws::String const &bucket,
                        Aws::String const &key,
                          double& write_units,
                          int size,
                          unsigned char* pBuf);

};

