import { Controller, useForm } from 'react-hook-form';
import { useTenureGalleriesQuery, useUpdateGallery, useCreateGallery } from '../queries';
import type { TenureGallery } from '../types';
import MyTenureSelect from '@/components/MyTenureSelect';
import TenureMultiSearch from '@/components/TenureMultiSearch';
import { SubmitButton } from '@/components/SubmitButton';
import type { Option } from '@/shared/types';

interface GalleryFormValues {
  is_public: boolean;
  viewers: Option<number>[];
}

function GalleryForm({ gallery, onSave }: { gallery: TenureGallery; onSave: () => void }) {
  const { register, control, handleSubmit, watch } = useForm<GalleryFormValues>({
    defaultValues: {
      is_public: gallery.is_public,
      viewers: gallery.allowed_viewers.map((id) => ({ value: id, label: String(id) })),
    },
  });
  const updateGallery = useUpdateGallery();
  const isPublic = watch('is_public');
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
      {!isPublic && (
        <Controller
          name="viewers"
          control={control}
          render={({ field }) => (
            <TenureMultiSearch
              value={field.value}
              onChange={field.onChange}
              label="Allowed Viewer Tenures"
            />
          )}
        />
      )}
      <SubmitButton
        className="rounded bg-blue-500 px-2 py-1 text-white"
        isLoading={updateGallery.isPending}
      >
        Save
      </SubmitButton>
    </form>
  );
}

interface NewGalleryValues {
  name: string;
  is_public: boolean;
  viewers: Option<number>[];
}

function NewGalleryForm({ tenureId, onCreate }: { tenureId: number; onCreate: () => void }) {
  const {
    register,
    control,
    handleSubmit,
    reset,
    watch,
    formState: { isValid },
  } = useForm<NewGalleryValues>({
    defaultValues: { name: '', is_public: true, viewers: [] },
    mode: 'onChange',
  });
  const createGallery = useCreateGallery();
  const isPublic = watch('is_public');
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
      {!isPublic && (
        <Controller
          name="viewers"
          control={control}
          render={({ field }) => (
            <TenureMultiSearch
              value={field.value}
              onChange={field.onChange}
              label="Allowed Viewer Tenures"
            />
          )}
        />
      )}
      <SubmitButton
        className="rounded bg-blue-500 px-2 py-1 text-white"
        isLoading={createGallery.isPending}
        disabled={!isValid}
      >
        Create
      </SubmitButton>
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
        render={({ field }) => (
          <MyTenureSelect value={field.value} onChange={field.onChange} label="Gallery Owner" />
        )}
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
