-- POST 下单压测脚本

math.randomseed(os.time())

local order_path = "/api/v1/orders"
local order_body = os.getenv("WRK_ORDER_BODY")

if not order_body or order_body == "" then
  order_body = [[
{
  "items": [
    {
      "product_id": 1,
      "quantity": 1,
      "spec_option_ids": []
    }
  ],
  "order_type": "pickup",
  "guest_session_id": "guest-perf-001",
  "notes": "wrk 压测"
}
]]
end

local bearer = os.getenv("WRK_BEARER_TOKEN") or ""
if bearer ~= "" and not string.find(bearer:lower(), "bearer ") then
  bearer = "Bearer " .. bearer
end

local prefix = os.getenv("WRK_IDEMPOTENCY_PREFIX") or "wrk-perf"
local thread_seed = 0
local counter = 0

function setup(thread)
  thread:set("seed", math.random(100000, 999999))
end

function init(args)
  counter = 0
  thread_seed = tonumber(wrk.thread:get("seed"))
  math.randomseed(os.time() + thread_seed)
end

function request()
  counter = counter + 1
  local headers = {
    ["Content-Type"] = "application/json",
    ["Idempotency-Key"] = string.format("%s-%d-%d", prefix, thread_seed, counter),
  }

  if bearer ~= "" then
    headers["Authorization"] = bearer
  end

  return wrk.format("POST", order_path, headers, order_body)
end
