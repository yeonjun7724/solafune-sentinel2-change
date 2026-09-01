<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <!-- Styled on ml_anomaly_quantile (rank percentile, always in [0,1] by construction),
       not the raw ml_anomaly_score, so this static style is valid across runs.
       EXPERIMENTAL: exploratory anomaly ranking, not a validated probability. -->
  <renderer-v2 type="graduatedSymbol" attr="ml_anomaly_quantile" graduatedMethod="GraduatedColor">
    <ranges>
      <range lower="0.0" upper="0.5" label="Below median anomaly rank" symbol="0"/>
      <range lower="0.5" upper="0.9" label="Above median (top 50%)" symbol="1"/>
      <range lower="0.9" upper="1.01" label="Top 10% anomaly rank" symbol="2"/>
    </ranges>
    <symbols>
      <symbol type="fill" name="0"><layer class="SimpleFill"><Option><Option name="color" value="247,251,255,60"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="1"><layer class="SimpleFill"><Option><Option name="color" value="107,174,214,140"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="2"><layer class="SimpleFill"><Option><Option name="color" value="8,48,107,200"/><Option name="outline_width" value="0"/></Option></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
