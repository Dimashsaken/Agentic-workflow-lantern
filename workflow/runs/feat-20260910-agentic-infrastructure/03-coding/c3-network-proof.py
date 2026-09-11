"""Actual disposable Linux kernel rules, not native-host adapter acceptance.

Runs with no Docker socket, no host networking/PIDs and no external route.
Containers/namespaces here are test-only; publication/activation remains disabled.
"""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

sys.path.insert(0,'/source/tools/azure-runner')
from qa_network import rule_plan,normalize_rules
from qa_transport import Policy,Destination

def command(*args,input=None):
    p=subprocess.run(args,input=input,capture_output=True,text=True,timeout=20)
    if p.returncode: raise RuntimeError(str(args)+': '+p.stderr)
    return p.stdout

def ns(name,*args,input=None):
    return command('ip','netns','exec',name,*args,input=input)

def client(namespace,address,port,udp=False):
    program="""import socket,sys
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if sys.argv[3]=='udp' else socket.SOCK_STREAM)
s.settimeout(.5)
try:
 s.connect((sys.argv[1],int(sys.argv[2])));s.send(b'probe');assert s.recv(100)==b'ok';print('ok')
except (OSError,AssertionError):print('denied')
finally:s.close()
"""
    return ns(namespace,'python3','-c',program,address,str(port),'udp' if udp else 'tcp').strip()

server=r"""import socket,threading,time
from pathlib import Path
for port,udp in [(8443,False),(8444,False),(53,True),(443,True)]:
 def serve(port=port,udp=udp):
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM);s.bind(('0.0.0.0',port))
  if not udp:s.listen()
  while True:
   if udp:
    data,peer=s.recvfrom(100);s.sendto(b'ok',peer)
   else:
    c,peer=s.accept();c.recv(100);c.sendall(b'ok');c.close()
   with open('/tmp/observations','a') as f:f.write(str(port)+'\n')
 threading.Thread(target=serve,daemon=True).start()
time.sleep(300)
"""
proxy="""import socket,time
s=socket.socket();s.bind(('10.210.1.1',8080));s.listen()
while True:
 c,p=s.accept();c.recv(100)
 try:
  u=socket.create_connection(('10.210.2.2',8443),1);u.sendall(b'proxy');c.sendall(u.recv(100));u.close()
 except OSError:pass
 c.close()
"""
processes=[]
results={}
try:
 for name in ('r','g','u'):command('ip','netns','add',name);ns(name,'ip','link','set','lo','up')
 for first,second,subnet in [('r','g',1),('g','u',2)]:
  a,b=first+str(subnet),second+str(subnet)
  command('ip','link','add',a,'type','veth','peer','name',b)
  command('ip','link','set',a,'netns',first);command('ip','link','set',b,'netns',second)
  for name,device,last in [(first,a,2 if subnet==1 else 1),(second,b,1 if subnet==1 else 2)]:
   ns(name,'ip','addr','add',f'10.210.{subnet}.{last}/24','dev',device);ns(name,'ip','link','set',device,'up')
 ns('r','ip','route','add','default','via','10.210.1.1')
 ns('u','ip','route','add','default','via','10.210.2.1')
 ns('g','sh','-c','mount -o remount,rw /proc/sys && sysctl -w net.ipv4.ip_forward=1')
 processes.append(subprocess.Popen(['ip','netns','exec','u','python3','-c',server]))
 processes.append(subprocess.Popen(['ip','netns','exec','g','python3','-c',proxy]))
 time.sleep(.3)
 # Calibrate observers before restriction: removing the boundary permits every
 # forbidden port. A failed denied probe alone is insufficient evidence.
 for label,port,udp in [('direct',8444,False),('dns',53,True),('quic',443,True)]:
  results['permissive_'+label]=client('r','10.210.2.2',port,udp)
  assert results['permissive_'+label]=='ok',results
 policy=Policy('proof:1',[Destination('https://allowed.test:8443',('10.210.2.2',),time.time()+120)],test_only=True).document()
 for name,role in [('r','recorder'),('g','gateway')]:
  plan=rule_plan(role,'10.210.1.1',8080,'10.210.1.2',policy)
  ns(name,'nft','-j','-f','-',input=json.dumps(plan))
  actual=json.loads(ns(name,'nft','-j','list','table','inet','lantern_qa'))
  if normalize_rules(actual)!=normalize_rules(plan,planned=True):
   Path('/tmp/readback.json').write_text(json.dumps({'plan':plan,'actual':actual}))
   raise RuntimeError('nft readback normalization differs: '+json.dumps({'plan':plan,'actual':actual}))
 results['proxy_positive']=client('r','10.210.1.1',8080)
 assert results['proxy_positive']=='ok',results
 before=Path('/tmp/observations').read_text().splitlines()
 for label,namespace,address,port,udp in [
  ('direct_tcp','r','10.210.2.2',8443,False),('alternate_proxy_port','r','10.210.1.1',8444,False),
  ('direct_dns','r','10.210.2.2',53,True),('quic','r','10.210.2.2',443,True),
  ('gateway_forbidden_port','g','10.210.2.2',8444,False),('metadata','r','169.254.169.254',80,False)]:
  results[label]=client(namespace,address,port,udp);assert results[label]=='denied',results
 # Exercise Docker-style DNS DNAT ordering, not a claim of a Desktop adapter.
 ns('r','nft','-f','-',input='table ip simulated_docker_dns { chain output { type nat hook output priority -100; ip daddr 127.0.0.11 udp dport 53 dnat to 10.210.2.2:53; }; }')
 results['embedded_dns_before_dnat']=client('r','127.0.0.11',53,True)
 assert results['embedded_dns_before_dnat']=='denied'
 after=Path('/tmp/observations').read_text().splitlines()
 assert before==after,{'unauthorized_upstream_observations':after[len(before):]}
 results['zero_forbidden_upstream_bytes']=True
 print(json.dumps({'passed':True,'scope':'actual nft kernel rules in disposable Linux namespaces; native host adapter and external TLS integration unaccepted','results':results}))
finally:
 for p in processes:p.terminate()
 for p in processes:p.wait(timeout=10)
