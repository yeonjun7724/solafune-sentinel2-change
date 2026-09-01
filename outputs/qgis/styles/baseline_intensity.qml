<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <pipe>
    <rasterrenderer band="1" type="singlebandpseudocolor" opacity="1" alphaBand="-1" classificationMin="0.0" classificationMax="1.0">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="1">
          <item value="0.0" color="#ffffff00" alpha="0" label="No change"/>
          <item value="0.33" color="#ffff6600" alpha="180" label="Moderate"/>
          <item value="0.66" color="#ff0000" alpha="230" label="Strong"/>
          <item value="1.0" color="#800026" alpha="255" label="Very strong"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
  </pipe>
</qgis>
