# bambu-mqtt-extractor

This is a fully AI generated and maintained project; none of it has been reviewed by a human. It extracts data about the MQTT message format from the Bambu Studio source code (used for printer communication) and converts that into JSON data that can be ingested by other programs. The idea is that this JSON data can be used to create communication libraries in other languages that can be updated by quickly re-extracting new JSON config files from the updated Bambu Studio code. Since this code just parses the static Bambu Studio codebase, there's a good chance that future re-extraction attempts will regularly break this code, but be easily fixable by another AI pass.

Much of this code is probably garbage since the first pass was generated using a free OpenCode model. The only outputs I made Claude directly validate/fix are related to AMS control and changing filament settings, specifically the parts used by https://github.com/Aptimex/bambu-mqtt-generator. 

## License
MIT