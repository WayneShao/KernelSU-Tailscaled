# Strict JSON reader for Android shells without jq. Only allowlisted fields
# leave the process; Persist and authentication URLs never do.
function fail() { bad = 1; exit 1 }
function ws() { while (pos <= length(input) && substr(input, pos, 1) ~ /[ \t\r\n]/) pos++ }
function string(    start,c,e) {
    start = pos++
    while (pos <= length(input)) {
        c = substr(input,pos++,1)
        if (c == "\"") return substr(input,start,pos-start)
        if (c ~ /[[:cntrl:]]/) fail()
        if (c == "\\") {
            e = substr(input,pos++,1)
            if (e == "u") {
                if (substr(input,pos,4) !~ /^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$/) fail()
                pos += 4
            } else if (e !~ /^["\\\/bfnrt]$/) fail()
        }
    }
    fail()
}
function parse(depth,    id,c,k,child,token,start) {
    if (depth > 40 || count > 40000) fail()
    ws(); id = ++count; c = substr(input,pos,1)
    if (c == "{" || c == "[") {
        type[id] = c; pos++; ws()
        if (substr(input,pos,1) == (c=="{" ? "}" : "]")) {pos++; return id}
        while (1) {
            if (c == "{") {
                if (substr(input,pos,1) != "\"") fail()
                k = string(); ws()
                if (seen[id,k]++) fail()
                if (substr(input,pos++,1) != ":") fail()
            } else k = ""
            child = parse(depth+1); key[child] = k
            if (!first[id]) first[id] = child; else nextnode[last[id]] = child
            last[id] = child; ws(); token = substr(input,pos++,1)
            if (token == (c=="{" ? "}" : "]")) break
            if (token != ",") fail()
            ws()
        }
    } else if (c == "\"") { type[id] = "string"; value[id] = string() }
    else {
        start=pos
        while (pos<=length(input) && index(" \t\r\n,}]", substr(input,pos,1)) == 0) pos++
        token=substr(input,start,pos-start)
        if (token !~ /^(true|false|null)$/ && token !~ /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$/) fail()
        type[id]="scalar"; value[id]=token
    }
    return id
}
function member(id,name,    i) { for(i=first[id];i;i=nextnode[i]) if(key[i]=="\"" name "\"") return i; return 0 }
function clean(s, lower) {
    lower=tolower(s)
    if(lower ~ /(privkey:|nodekey:|tskey-|private[a-z_-]*key|bearer |authorization|password|secret|token)/) return "\"[REDACTED]\""
    gsub(/(https?|socks5):\/\/[^ "\\]+/, "[REDACTED_URL]", s)
    return s
}
function emit(id,context,    i,k,out,child,allowed,sep) {
    if (!id) return "null"
    if(type[id]=="string") return clean(value[id])
    if(type[id]=="scalar") return value[id]
    out=type[id]; sep=""
    for(i=first[id];i;i=nextnode[i]) {
        k=substr(key[i],2,length(key[i])-2); allowed=1; child=context
        if(type[id]=="{") {
            if(context=="status") {
                allowed=(k ~ /^(BackendState|TailscaleIPs|Self|Peer|Health|Version|CurrentTailnet)$/)
                child=(k=="Self" ? "peer" : k=="Peer" ? "peers" : k=="CurrentTailnet" ? "tailnet" : "leaf")
            } else if(context=="prefs") {
                allowed=(k ~ /^(Hostname|CorpDNS|RouteAll|ExitNodeIP|ExitNodeID|AdvertiseRoutes|WantRunning|LoggedOut|ShieldsUp|RunSSH|ExitNodeAllowLANAccess)$/); child="leaf"
            } else if(context=="peers") child="peer"
            else if(context=="peer") {allowed=(k ~ /^(ID|DNSName|HostName|TailscaleIPs|Online|OS|CurAddr|Relay|Active|LastSeen|LastHandshake|ExitNode|ExitNodeOption)$/); child="leaf"}
            else if(context=="tailnet") {allowed=(k ~ /^(Name|MagicDNSSuffix|MagicDNSEnabled)$/); child="leaf"}
            else allowed=0
        }
        if(allowed) {out=out sep (type[id]=="{" ? key[i] ":" : "") emit(i,child); sep=","}
    }
    return out (type[id]=="{" ? "}" : "]")
}
function ips(id,    i,s) {
    if(type[id]!="[") return
    for(i=first[id];i;i=nextnode[i]) {
        s=substr(value[i],2,length(value[i])-2)
        if(type[i]=="string" && s ~ /^[0-9a-fA-F:.]+$/) print s
    }
}
{ input=input $0 "\n"; if(length(input)>524288) fail() }
END {
    if(bad) exit 1
    pos=1; root=parse(0); ws()
    if(pos<=length(input) || type[root]!="{") fail()
    if(action=="status" || action=="prefs") {
        if(action=="status" && type[member(root,"BackendState")]!="string") fail()
        print emit(root,action)
    } else if(action=="backend") {
        id=member(root,"BackendState"); if(type[id]!="string") fail()
        print substr(value[id],2,length(value[id])-2)
    } else if(action=="ips") ips(member(root,"TailscaleIPs"))
    else if(action=="peer-ips") {
        peers=member(root,"Peer")
        for(peer=first[peers];peer;peer=nextnode[peer]) ips(member(peer,"TailscaleIPs"))
    } else if(action=="hostname") {
        id=member(root,"Hostname"); if(type[id]=="string") print substr(value[id],2,length(value[id])-2)
    } else if(action=="warnings") {
        if(value[member(root,"CorpDNS")]=="true") print "dns"
        if(value[member(root,"RouteAll")]=="true") print "routes"
        id=member(root,"ExitNodeID"); if(value[id]!="" && value[id]!="\"\"" && value[id]!="null") print "exit"
        id=member(root,"ExitNodeIP"); if(value[id]!="" && value[id]!="\"\"" && value[id]!="null" && value[id]!="\"0.0.0.0\"") print "exit"
        if(first[member(root,"AdvertiseRoutes")]) print "advertised"
    } else if(action=="health") {
        id=member(root,"Health")
        for(i=first[id];i;i=nextnode[i]) if(type[i]=="string") print clean(value[i])
    } else fail()
}
