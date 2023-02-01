
#include <cstdint>
#include <string>

#include <aws/core/utils/memory/stl/AWSString.h>

#include <hiredis/hiredis.h>

class Redis
{
  redisContext* _context;
public:

  Redis(std::string redis_hostname, int redis_port);
  ~Redis();

  bool is_initialized();

  uint64_t download_file(Aws::String const &key, int &required_retries, bool with_backoff);

  uint64_t upload_file(Aws::String const &key, int size, char* pBuf);

  uint64_t delete_file(std::string const &key);

};

