<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <renderer-v2 type="graduatedSymbol" attr="confidence" graduatedMethod="GraduatedColor">
    <ranges>
      <range lower="0.0" upper="0.3" label="Low confidence (0.0-0.3)" symbol="0"/>
      <range lower="0.3" upper="0.6" label="Medium confidence (0.3-0.6)" symbol="1"/>
      <range lower="0.6" upper="1.01" label="High confidence (0.6-1.0)" symbol="2"/>
    </ranges>
    <symbols>
      <symbol type="fill" name="0" alpha="0.35"><layer class="SimpleFill"><Option><Option name="color" value="255,255,0,90"/><Option name="outline_color" value="255,255,0,255"/><Option name="outline_width" value="0.3"/></Option></layer></symbol>
      <symbol type="fill" name="1" alpha="0.45"><layer class="SimpleFill"><Option><Option name="color" value="255,140,0,120"/><Option name="outline_color" value="255,140,0,255"/><Option name="outline_width" value="0.4"/></Option></layer></symbol>
      <symbol type="fill" name="2" alpha="0.55"><layer class="SimpleFill"><Option><Option name="color" value="220,20,20,150"/><Option name="outline_color" value="220,20,20,255"/><Option name="outline_width" value="0.5"/></Option></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
