"""Test-only Android 10+ dnsproxyd resnsend responder in a private /dev mount."""
import base64, socket, struct
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.bind('/dev/socket/dnsproxyd');s.listen(8)
while True:
 c,_=s.accept()
 with c:
  data=c.recv(1024).rstrip(b'\0')
  if not data: continue # Android feature startup availability check
  fields=data.split()
  if len(fields)!=4 or fields[:3]!=[b'resnsend',b'0',b'0']:
   c.sendall(b'500 Command not recognized\0');continue
  query=base64.b64decode(fields[3],validate=True)
  pos=12
  while query[pos]: pos+=query[pos]+1
  end=pos+5
  qtype=struct.unpack('!H',query[pos+1:pos+3])[0]
  count=1 if qtype==1 else 0
  answer=query[:2]+struct.pack('!HHHHH',0x8180,1,count,0,0)+query[12:end]
  if count:answer+=b'\xc0\x0c'+struct.pack('!HHIH',1,1,60,4)+socket.inet_aton('192.0.2.2')
  c.sendall(struct.pack('!ii',0,len(answer))+answer)
