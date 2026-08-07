import { format } from "date-fns";
import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { UpcomingItem } from "@/lib/analytics";

type UpcomingCardProps = {
  upcoming: UpcomingItem[];
};

export function UpcomingCard({ upcoming }: UpcomingCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Upcoming</CardTitle>
        <CardDescription>Interviews and events in the future</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {upcoming.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing scheduled</p>
        ) : (
          upcoming.map((item, index) => (
            <Link
              key={`${item.at}-${index}`}
              href={item.href}
              className="flex justify-between rounded-md border px-3 py-2 text-sm hover:bg-muted/50"
            >
              <span>{item.label}</span>
              <span className="text-muted-foreground">
                {format(new Date(item.at), "MMM d, HH:mm")}
              </span>
            </Link>
          ))
        )}
      </CardContent>
    </Card>
  );
}
