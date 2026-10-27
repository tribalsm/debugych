/** Local best-effort redaction; never needs provider credentials in the renderer. */
export function redactChat(value:string){return value
 .replace(/-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z ]+ )?PRIVATE KEY-----|$)/g,'[СЕКРЕТ УДАЛЁН]')
 .replace(/\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{15,}|AKIA[A-Z0-9]{16})\b/g,'[СЕКРЕТ УДАЛЁН]')
 .replace(/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,'[СЕКРЕТ УДАЛЁН]')
 .replace(/\bBearer\s+[A-Za-z0-9._~+/-]{8,}/gi,'[СЕКРЕТ УДАЛЁН]')
 .replace(/\b(?:api[_-]?key|secret|password|passwd|token|database_url)\s*[:=]\s*(?:"[^"\r\n]+"|'[^'\r\n]+'|[^\s\r\n]+)/gi,'[СЕКРЕТ УДАЛЁН]')
 .replace(/\b[a-z][a-z0-9+.-]{0,20}:\/\/[^\s/:]+:[^\s/@]+@[^\s"'<>]+/gi,'[СЕКРЕТ УДАЛЁН]');}
