function redacted(line, lowered) {
    lowered = tolower(line)
    if (lowered ~ /(private[a-z_-]*key|privkey:|nodekey:|tskey-|authorization|bearer[ :]|token[" =:]|password[" =:]|secret[" =:]|authurl)/)
        return "[REDACTED sensitive log entry]"
    gsub(/(https?|socks5):\/\/[^[:space:]"<>]+/, "[REDACTED_URL]", line)
    return substr(line, 1, 2048)
}
BEGIN {
    size = 0
    if (destination != "") {
        while ((getline old < destination) > 0) size += length(old) + 1
        close(destination)
    }
}
{
    line = redacted($0)
    if (destination == "") print line
    else {
        if (size + length(line) + 1 > 262144) {
            close(destination)
            printf "%s", "" > destination
            close(destination)
            size = 0
        }
        print line >> destination
        close(destination)
        size += length(line) + 1
    }
}
