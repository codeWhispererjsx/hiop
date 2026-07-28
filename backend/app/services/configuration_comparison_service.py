import difflib, hashlib, re
class ConfigurationComparisonService:
    SECRET=re.compile(r"(?i)(password|secret|community|token|private[-_ ]?key)\s*[:=]\s*([^\s]+)")
    @classmethod
    def normalize(cls,text:str)->str: return "\n".join(line.rstrip() for line in text.replace("\r\n","\n").replace("\r","\n").splitlines()).strip()+"\n"
    @classmethod
    def redact(cls,text:str)->str: return cls.SECRET.sub(lambda m:f"{m.group(1)}=[REDACTED]",text)
    @classmethod
    def diff(cls,source:str,target:str):
        a=cls.redact(cls.normalize(source)).splitlines(); b=cls.redact(cls.normalize(target)).splitlines(); changes=list(difflib.unified_diff(a,b,n=2)); added=sum(1 for x in changes if x.startswith("+") and not x.startswith("+++")); removed=sum(1 for x in changes if x.startswith("-") and not x.startswith("---")); return {"added_lines":added,"removed_lines":removed,"change_count":added+removed,"risk_level":"medium" if added+removed else "none","diff":"\n".join(changes),"normalized_source_checksum":hashlib.sha256("\n".join(a).encode()).hexdigest(),"normalized_target_checksum":hashlib.sha256("\n".join(b).encode()).hexdigest()}
