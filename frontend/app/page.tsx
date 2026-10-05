import HomeShows from '@/components/HomeShows'

// Static page: the Shows are loaded in the browser from the exported JSON (python -m app.cli export).
export default function Home() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold">This Week&apos;s Shows</h1>
      <HomeShows />
    </div>
  )
}
