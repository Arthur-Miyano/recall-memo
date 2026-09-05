"""在启动端口范围内快速查找已经运行的本应用。"""
import http.client


for port in range(8000, 8020):
    connection = None
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.3)
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        if response.status == 200 and b'"local_token"' in response.read():
            print(port)
            break
    except (OSError, http.client.HTTPException):
        pass
    finally:
        if connection:
            connection.close()
