"use client";
import { useEffect, useState } from "react";
import { workflowRequest } from "@/lib/session";
type Day = { weekday: number; start: string; end: string };
const names = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
export default function DoctorSchedule() {
  const [days, setDays] = useState<Day[]>([]),
    [duration, setDuration] = useState(30),
    [leave, setLeave] = useState(""),
    [message, setMessage] = useState(""),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    workflowRequest("doctor/schedule")
      .then((s) => {
        setDays(s.days);
        setDuration(s.duration_minutes);
        setLeave(s.leave_dates.join(", "));
        setReady(true);
      })
      .catch((e) => setMessage(e.message));
  }, []);
  return (
    <details className="bg-white rounded-xl p-5 border mb-6">
      <summary className="font-bold cursor-pointer">
        Manage working hours and leave
      </summary>
      <form
        className="space-y-3 mt-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const r = await workflowRequest(
              "doctor/schedule",
              {
                days,
                duration_minutes: duration,
                leave_dates: leave
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              },
              "PUT",
            );
            setMessage(r.message);
          } catch (e) {
            setMessage(e instanceof Error ? e.message : "Save failed");
          } finally {
            setBusy(false);
          }
        }}
      >
        <p>
          Hospital-local time. Existing appointments must fit the new schedule.
        </p>
        {names.map((name, weekday) => {
          const day = days.find((d) => d.weekday === weekday);
          return (
            <div key={name} className="flex gap-3 items-center">
              <label>
                <input
                  type="checkbox"
                  checked={!!day}
                  onChange={(e) =>
                    setDays(
                      e.target.checked
                        ? [...days, { weekday, start: "09:00", end: "17:00" }]
                        : days.filter((d) => d.weekday !== weekday),
                    )
                  }
                />{" "}
                {name}
              </label>
              {day && (
                <>
                  <input
                    aria-label={`${name} start`}
                    type="time"
                    value={day.start}
                    onChange={(e) =>
                      setDays(
                        days.map((d) =>
                          d.weekday === weekday
                            ? { ...d, start: e.target.value }
                            : d,
                        ),
                      )
                    }
                  />
                  <input
                    aria-label={`${name} end`}
                    type="time"
                    value={day.end}
                    onChange={(e) =>
                      setDays(
                        days.map((d) =>
                          d.weekday === weekday
                            ? { ...d, end: e.target.value }
                            : d,
                        ),
                      )
                    }
                  />
                </>
              )}
            </div>
          );
        })}
        <label className="block">
          Appointment duration (minutes)
          <input
            aria-label="Appointment duration"
            className="border p-2 ml-3"
            type="number"
            min={5}
            max={240}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
        </label>
        <label className="block">
          Leave dates (YYYY-MM-DD, comma separated)
          <input
            className="block border p-2 w-full"
            value={leave}
            onChange={(e) => setLeave(e.target.value)}
          />
        </label>
        <button
          disabled={!ready || busy}
          className="bg-cyan-700 text-white rounded px-4 py-2"
        >
          Save availability
        </button>
        <p role="status">{message}</p>
      </form>
    </details>
  );
}
