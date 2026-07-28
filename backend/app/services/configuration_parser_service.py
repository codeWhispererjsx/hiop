import json
class ConfigurationParserService:
    @staticmethod
    def parse(text:str, parser_type="generic_text"):
        if len(text)>10_000_000: raise ValueError("configuration exceeds parser limit")
        if parser_type.lower()=="json": return json.loads(text)
        return {"lines": text.replace("\r\n","\n").replace("\r","\n").splitlines(),"line_count":len(text.splitlines())}
