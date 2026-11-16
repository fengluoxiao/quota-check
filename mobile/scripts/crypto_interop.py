"""Cross-check the actual Swift/C codec against the existing desktop portable format."""
import base64,http.server,json,subprocess,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import vault
executable=sys.argv[1]
password='native-portable-test-password-2026'
profile={'version':1,'source':0,'profiles':{'glm':{'site':'cn','key':'test-interop-key','sealed':False}}}
def native(body,success=True):
    p=subprocess.run([executable],input=json.dumps(body).encode(),capture_output=True,timeout=30)
    result=json.loads(p.stdout)
    assert result['ok'] is success,result
    return result
blob=vault.encode(profile,password=password)
opened=native({'op':'open','blob':base64.b64encode(blob).decode(),'secret':password})
assert json.loads(opened['plaintext'])==profile
sealed=native({'op':'seal','plaintext':json.dumps(profile),'secret':password,'mode':1})
assert vault.decode(base64.b64decode(sealed['blob']),password=password)==profile
native({'op':'open','blob':sealed['blob'],'secret':'wrong-file-password'},False)
damaged=bytearray(base64.b64decode(sealed['blob']));damaged[-1]^=1
native({'op':'open','blob':base64.b64encode(damaged).decode(),'secret':password},False)
key=base64.b64encode(bytes(range(32))).decode()
local=native({'op':'seal','plaintext':json.dumps(profile),'secret':key,'mode':2})
assert json.loads(native({'op':'open','blob':local['blob'],'secret':key})['plaintext'])==profile
print('Swift/C and Python portable .sqv round-trips, device encryption, bad password and tamper rejection passed.')
class Handler(http.server.BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args):pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)));self.calls.append(self.path)
        if self.path=='/redirect':self.send_response(307);self.send_header('Location','/must-not-receive-secrets');self.end_headers()
        else:self.send_response(200);self.end_headers()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    response=native({'op':'http','url':'http://127.0.0.1:'+str(server.server_port)+'/redirect','method':'POST','headers':{'Authorization':'test-only'},'body':'test-only'})
    assert response['status']==307 and Handler.calls==['/redirect'],Handler.calls
    print('Native URLSession refused credential-bearing redirects.')
finally:server.shutdown();server.server_close()
