import { Controller, useForm } from 'react-hook-form';
import Select from 'react-select';
import CreatableSelect from 'react-select/creatable';
import { useMyRosterEntriesQuery, useTenureGalleriesQuery, useUpdateGallery } from '../queries';
import type { TenureGallery } from '../types';

interface Option {
  value: number;
  label: string;
}

interface GalleryFormValues {
  is_public: boolean;
  viewers: Option[];
}

function GalleryForm({ gallery, onSave }: { gallery: TenureGallery; onSave: () => void }) {
  const { register, control, handleSubmit } = useForm<GalleryFormValues>({
    defaultValues: {
      is_public: gallery.is_public,
      viewers: gallery.allowed_viewers.map((id) => ({ value: id, label: String(id) })),
    },
  });
  const updateGallery = useUpdateGallery();
  const onSubmit = async (data: GalleryFormValues) => {
    await updateGallery.mutateAsync({
      galleryId: gallery.id,
      data: { is_public: data.is_public, allowed_viewers: data.viewers.map((v) => v.value) },
    });
    onSave();
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-1">
      <p className="font-semibold">{gallery.name}</p>
      <label className="flex items-center space-x-2">
        <input type="checkbox" {...register('is_public')} /> <span>Public</span>
      </label>
      <Controller
        name="viewers"
        control={control}
        render={({ field }) => (
          <CreatableSelect
            {...field}
            isMulti
            placeholder="Allowed viewer tenure IDs"
            formatCreateLabel={(val) => `Add ${val}`}
          />
        )}
      />
      <button type="submit" className="rounded bg-blue-500 px-2 py-1 text-white">
        Save
      </button>
    </form>
  );
}

export function GalleryManagement() {
  const { data: myEntries } = useMyRosterEntriesQuery();
  const { control, watch } = useForm<{ tenure: Option | null }>({
    defaultValues: { tenure: null },
  });
  const tenureId = watch('tenure')?.value;
  const { data: galleries, refetch } = useTenureGalleriesQuery(tenureId);

  const tenureOptions = myEntries?.map((e) => ({ value: e.id, label: e.name })) ?? [];

  return (
    <section className="space-y-2">
      <h3 className="text-lg font-semibold">Manage Galleries</h3>
      <Controller
        name="tenure"
        control={control}
        render={({ field }) => (
          <Select {...field} options={tenureOptions} isClearable placeholder="Select Tenure" />
        )}
      />
      <ul className="space-y-2">
        {galleries?.map((g) => (
          <li key={g.id} className="border p-2">
            <GalleryForm gallery={g} onSave={() => refetch()} />
          </li>
        ))}
      </ul>
    </section>
  );
}
