import { ContactDetail } from "@/components/contacts/contact-detail";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ContactDetail id={id} />;
}
