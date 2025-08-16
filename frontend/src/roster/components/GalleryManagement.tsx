import { Controller, useForm } from 'react-hook-form';
import CreatableSelect from 'react-select/creatable';
import { useTenureGalleriesQuery, useUpdateGallery, useCreateGallery } from '../queries';
import type { TenureGallery } from '../types';
import MyTenureSelect from '@/components/MyTenureSelect';

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

interface NewGalleryValues {
  name: string;
  is_public: boolean;
  viewers: Option[];
}

function NewGalleryForm({ tenureId, onCreate }: { tenureId: number; onCreate: () => void }) {
  const { register, control, handleSubmit, reset } = useForm<NewGalleryValues>({
    defaultValues: { name: '', is_public: true, viewers: [] },
  });
  const createGallery = useCreateGallery();
  const onSubmit = async (data: NewGalleryValues) => {
    await createGallery.mutateAsync({
      tenureId,
      data: {
        name: data.name,
        is_public: data.is_public,
        allowed_viewers: data.viewers.map((v) => v.value),
      },
    });
    reset();
    onCreate();
  };
  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-1">
      <input type="text" placeholder="New gallery name" {...register('name', { required: true })} />
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
        Create
      </button>
    </form>
  );
}

export function GalleryManagement() {
  const { control, watch } = useForm<{ tenure: number | null }>({
    defaultValues: { tenure: null },
  });
  const tenureId = watch('tenure');
  const { data: galleries, refetch } = useTenureGalleriesQuery(tenureId ?? undefined);

  return (
    <section className="space-y-2">
      <h3 className="text-lg font-semibold">Manage Galleries</h3>
      <Controller
        name="tenure"
        control={control}
        render={({ field }) => <MyTenureSelect value={field.value} onChange={field.onChange} />}
      />
      {tenureId && <NewGalleryForm tenureId={tenureId} onCreate={() => refetch()} />}
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
