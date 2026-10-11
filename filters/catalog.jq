# Informational templates only; identity is not guaranteed unique by DSRT.
if type != "array" then error("DSRT catalog: expected array")
elif length == 0 then error("DSRT catalog: empty response") else . end
| map(
    if type != "object" then error("DSRT catalog: invalid product") else . end
    | if (.id|type) != "string" or (.name|type) != "string" or (.price|type) != "number"
      then error("DSRT catalog: invalid identity/name/price") else . end
    | {id, name, price:(.price + 0), waveClass, waveCode, skill, skillLevels: ((.skillLevels // []) | sort)}
  )
| unique
| sort_by(.id, .name, .waveCode, .skill, .price, .skillLevels)
