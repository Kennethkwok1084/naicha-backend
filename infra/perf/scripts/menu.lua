-- GET 菜单接口压测脚本

wrk.method = "GET"

function request()
  return wrk.format(nil, "/api/v1/menu")
end
