# Fail closed: errors must never replace a valid pricing snapshot.
def fail($message): error("DSRT: " + $message);
def nonempty_string: type == "string" and length > 0;
if type != "array" then fail("expected an array")
elif length == 0 then fail("empty schedule") else . end
| if all(.[]; type == "object" and (.waveClass | nonempty_string) and (.audience | nonempty_string)
    and ((.privateSession == null) or (.privateSession | type == "boolean")))
  then . else fail("invalid session classification") end
| map(select(.waveClass == "reef" and .audience == "public" and .privateSession != true))
| if length == 0 then fail("no public reef sessions") else . end
| map(
    if (.sessiontype | nonempty_string)
       and (.dateid | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
       and (.starttime | type == "string" and test("^([01][0-9]|2[0-3]):[0-5][0-9]$"))
    then . else fail("invalid session name/date/time") end
    | . as $s
    | (if .currentPrice == null then .price else .currentPrice end) as $price
    | if ($price | type != "number") then fail("invalid effective price")
      elif $price < 0 then fail("negative effective price") else . end
    | ($s.dateid | strptime("%Y-%m-%d")) as $date
    | if ($date | strftime("%Y-%m-%d")) != $s.dateid then fail("invalid date") else . end
    | {session: $s.sessiontype, day: (["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"][$date[6]]), time: $s.starttime, price: ($price + 0)}
  )
| group_by([.session, .day, .time])
| map({session: .[0].session, day: .[0].day, time: .[0].time, prices: (map(.price) | unique)})
| sort_by(.session, .day, .time)
